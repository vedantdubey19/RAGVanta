import csv
import hmac
import io
import json
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exception_handlers import http_exception_handler
from pathlib import Path
from urllib.parse import urlparse
from app.auth import Auth, COOKIE, CSRF_COOKIE, digest
from app.quotas import BudgetExceeded, prune_expired
import asyncio
import contextlib
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.config import Settings
from app.evaluation import load_scenarios, run_experiment
from app.models import ProviderError
from app.service import Laboratory


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CollectionRequest(StrictModel):
    name: str = Field(min_length=1, max_length=100)


class ChatRequest(StrictModel):
    question: str = Field(min_length=1, max_length=2000)
    collection_id: str = Field(min_length=1, max_length=64)
    mode: Literal["baseline", "protected"] = "protected"
    top_k: int = Field(3, ge=1, le=5)


class ExperimentRequest(StrictModel):
    split: Literal["development", "held_out"] = "development"
    limit: int = Field(50, ge=1, le=50)
    offset: int = Field(0, ge=0, le=100)


def create_app(settings=None):
    config = settings or Settings()
    @asynccontextmanager
    async def lifespan(api):
        api.state.lab = Laboratory(config)
        api.state.auth = Auth(api.state.lab.store, config)
        with api.state.lab.store.connect() as db:
            for row in db.execute("SELECT id,report FROM runs WHERE status IN ('queued','running')").fetchall():
                report = json.loads(row["report"])
                report.update(status="interrupted", failure_reason="Service restarted before run completion")
                db.execute("UPDATE runs SET status=?,report=? WHERE id=?", ("interrupted", json.dumps(report), row["id"]))
        async def maintenance():
            while True:
                await asyncio.sleep(3600)
                await asyncio.to_thread(prune_expired, api.state.lab.store, config)
        await asyncio.to_thread(prune_expired, api.state.lab.store, config)
        task = asyncio.create_task(maintenance())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    api = FastAPI(title="RAGVanta", version="0.1.0", lifespan=lifespan,
                  description="Synthetic RAG security laboratory",
                  docs_url=None if config.deployment == "hosted" else "/docs",
                  redoc_url=None if config.deployment == "hosted" else "/redoc",
                  openapi_url=None if config.deployment == "hosted" else "/openapi.json")
    if config.deployment == "hosted":
        api.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlparse(config.public_url).hostname])

    def actor_lab(request):
        return request.app.state.lab.for_actor(request.state.actor)
    calls, rate_lock = deque(), threading.Lock()
    experiment_lock = threading.Lock()
    upload_slots = threading.BoundedSemaphore(2)

    @api.middleware("http")
    async def boundary(request: Request, call_next):
        host = request.client.host if request.client else ""
        path = request.url.path
        request.state.actor = config.actor_id
        public = path in ("/", "/health", "/auth/login") or path.startswith("/assets/")
        if config.deployment == "hosted":
            auth = request.app.state.auth
            if request.method not in ("GET", "HEAD"):
                if request.headers.get("origin") != config.public_url.rstrip("/"):
                    return Response("Origin denied", status_code=403)
            if not public:
                session = auth.session(request.cookies.get(COOKIE))
                if not session:
                    return Response("Authentication required", status_code=401)
                request.state.actor = session["user_id"]
                if request.method not in ("GET", "HEAD"):
                    csrf = request.headers.get("x-csrf-token", "")
                    if not hmac.compare_digest(digest(csrf), session["csrf_hash"]):
                        return Response("CSRF validation failed", status_code=403)
                if not auth.rate("api:" + request.state.actor, config.requests_per_minute):
                    return Response("Request rate exceeded", status_code=429, headers={"Retry-After": "60"})
        else:
            if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
                return Response("Local operator access only", status_code=403)
            if request.method not in ("GET", "HEAD"):
                origin = request.headers.get("origin")
                if origin and origin not in ("http://127.0.0.1:8501", "http://localhost:8501",
                                             "http://127.0.0.1:8000", "http://localhost:8000"):
                    return Response("Origin denied", status_code=403)
            if not public:
                supplied = request.headers.get("authorization", "")
                if config.api_token and not hmac.compare_digest(supplied, f"Bearer {config.api_token}"):
                    return Response("Unauthorized", status_code=401)
                with rate_lock:
                    now = time.monotonic()
                    while calls and calls[0] < now - 60:
                        calls.popleft()
                    if len(calls) >= config.requests_per_minute:
                        return Response("Request rate exceeded", status_code=429, headers={"Retry-After": "60"})
                    calls.append(now)
        # Count bytes before multipart parsing; rejects oversized bodies without spooling them.
        if request.method == "POST":
            maximum = config.max_file_bytes + 65536 if request.url.path == "/v1/documents" else 32768
            total, parts = 0, []
            async for part in request.stream():
                total += len(part)
                if total > maximum:
                    return Response("Payload limit exceeded", status_code=413)
                parts.append(part)
            body = b"".join(parts)
            request._body = body
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-Frame-Options"] = "DENY"
        if config.deployment == "hosted":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @api.middleware("http")
    async def upload_admission(request: Request, call_next):
        if request.method != "POST" or request.url.path != "/v1/documents":
            return await call_next(request)
        if not upload_slots.acquire(blocking=False):
            return Response("Upload concurrency limit reached", status_code=429)
        try:
            return await call_next(request)
        finally:
            upload_slots.release()


    @api.exception_handler(PermissionError)
    async def permission_error(request, exc):
        return Response("Collection unavailable", status_code=404)

    @api.exception_handler(ValueError)
    async def value_error(request, exc):
        return Response(str(exc), status_code=400)

    @api.exception_handler(OverflowError)
    async def overflow_error(request, exc):
        return Response(str(exc), status_code=413)

    @api.exception_handler(ProviderError)
    async def provider_error(request, exc):
        return Response("Model provider failed; check local configuration", status_code=502)

    @api.get("/health")
    def health():
        if config.deployment == "hosted":
            return {"status": "ok"}
        return {"status": "ok", "provider": config.provider, "model": config.model,
                "retrieval": config.retrieval, "scope": "local-single-operator"}

    @api.post("/v1/collections", status_code=201)
    def create_collection(body: CollectionRequest, request: Request):
        return actor_lab(request).create_collection(body.name)

    @api.get("/v1/collections")
    def collections(request: Request):
        return actor_lab(request).store.query("SELECT * FROM collections WHERE owner=?", (request.state.actor,))

    @api.delete("/v1/collections/{collection_id}", status_code=204)
    def delete_collection(collection_id: str, request: Request):
        actor_lab(request).delete_collection(collection_id)
        return Response(status_code=204)

    @api.post("/v1/documents", status_code=201)
    def ingest(request: Request, collection_id: str = Form(...), file: UploadFile = File(...), synthetic: bool = Form(False)):
        if config.deployment == "hosted" and not synthetic:
            raise HTTPException(400, "Confirm that the upload contains only synthetic test data")
        lab = actor_lab(request)
        lab.authorize(collection_id)
        data = file.file.read(config.max_file_bytes + 1)
        return lab.ingest(data, file.filename, collection_id)

    @api.get("/v1/documents")
    def documents(collection_id: str, request: Request):
        lab = actor_lab(request)
        lab.authorize(collection_id)
        return lab.store.query("SELECT documents.*, (SELECT COUNT(*) FROM chunks WHERE "
                               "document_id=documents.id) AS chunk_count FROM documents WHERE collection_id=?",
                               (collection_id,))

    @api.get("/v1/documents/{document_id}/chunks")
    def chunks(document_id: str, request: Request):
        lab = actor_lab(request)
        docs = lab.store.query("SELECT collection_id FROM documents WHERE id=?", (document_id,))
        if not docs:
            raise HTTPException(404, "Document unavailable")
        lab.authorize(docs[0]["collection_id"])
        return lab.store.query("SELECT * FROM chunks WHERE document_id=? ORDER BY page,start", (document_id,))

    @api.delete("/v1/documents/{document_id}", status_code=204)
    def delete_document(document_id: str, request: Request):
        lab = actor_lab(request)
        rows = lab.store.query("SELECT collection_id FROM documents WHERE id=?", (document_id,))
        if not rows:
            raise HTTPException(404, "Document unavailable")
        lab.authorize(rows[0]["collection_id"])
        ids = [r["id"] for r in lab.store.query("SELECT id FROM chunks WHERE document_id=?", (document_id,))]
        with lab.store.connect() as db:
            if ids:
                lab.retriever.delete(ids, db=db)
            db.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
            db.execute("DELETE FROM documents WHERE id=?", (document_id,))
        lab.store.event("document_deleted", "accepted", {"document_id": document_id, "actor_id": request.state.actor})
        return Response(status_code=204)

    @api.post("/v1/chat")
    def chat(body: ChatRequest, request: Request):
        return actor_lab(request).answer(**body.model_dump())

    @api.get("/v1/scenarios")
    def scenarios():
        return [{k: v for k, v in s.items() if k not in ("document", "marker")}
                for s in load_scenarios()]

    @api.post("/v1/experiments")
    def experiment(body: ExperimentRequest, request: Request):
        if not experiment_lock.acquire(blocking=False):
            raise HTTPException(409, "An experiment is already running")
        if config.deployment == "hosted":
            lab = actor_lab(request)
            scenarios = [s for s in load_scenarios() if s["split"] == body.split]
            if body.offset >= len(scenarios):
                experiment_lock.release()
                raise HTTPException(400, "No scenarios in selected batch")
            if len(lab.store.query("SELECT id FROM runs WHERE owner=?", (request.state.actor,))) >= config.max_experiment_runs:
                experiment_lock.release()
                raise HTTPException(413, "Retained experiment quota reached")
            run_id = uuid.uuid4().hex
            with lab.store.connect() as db:
                db.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (run_id, request.state.actor, time.time(), "queued",
                    json.dumps({"id": run_id, "status": "queued", "cases": [], "metrics": {}, "limitations": []})))
            def execute():
                try:
                    run_experiment(lab, body.split, body.limit, body.offset, run_id)
                except Exception:
                    with lab.store.connect() as db:
                        report = {"id": run_id, "status": "failed", "cases": [], "metrics": {},
                                  "limitations": ["Run initialization failed; inspect server configuration."]}
                        db.execute("UPDATE runs SET status=?, report=? WHERE id=?", ("failed", json.dumps(report), run_id))
                finally:
                    experiment_lock.release()
            threading.Thread(target=execute, daemon=True, name="ragvanta-experiment").start()
            return Response(json.dumps({"id": run_id, "status": "queued"}), status_code=202, media_type="application/json")
        try:
            return run_experiment(actor_lab(request), body.split, body.limit, body.offset)
        finally:
            experiment_lock.release()

    def report_for(request, run_id):
        rows = actor_lab(request).store.query("SELECT report FROM runs WHERE id=? AND owner=?",
                                                (run_id, request.state.actor))
        if not rows:
            raise HTTPException(404, "Run unavailable")
        return json.loads(rows[0]["report"])

    @api.get("/v1/experiments")
    def experiments(request: Request):
        return actor_lab(request).store.query("SELECT id,created,status FROM runs WHERE owner=? ORDER BY created DESC",
                                                (request.state.actor,))

    @api.get("/v1/experiments/{run_id}")
    def experiment_detail(run_id: str, request: Request):
        return report_for(request, run_id)

    @api.get("/v1/experiments/{run_id}/results")
    def experiment_results(run_id: str, request: Request):
        return report_for(request, run_id)["cases"]

    @api.delete("/v1/experiments/{run_id}", status_code=204)
    def delete_run(run_id: str, request: Request):
        report = report_for(request, run_id)
        if report["status"] in ("queued", "running"):
            raise HTTPException(409, "Cannot delete an active run")
        import shutil
        base = config.data_dir / "experiments" / run_id
        if base.is_dir() and not base.is_symlink():
            shutil.rmtree(base)
        with actor_lab(request).store.connect() as db:
            db.execute("DELETE FROM runs WHERE id=? AND owner=?", (run_id, request.state.actor))
        return Response(status_code=204)

    @api.get("/v1/reports/{run_id}")
    def export(run_id: str, request: Request, format: Literal["json", "csv"] = "json"):
        report = report_for(request, run_id)
        if format == "json":
            content, media = json.dumps(report, indent=2), "application/json"
        else:
            output = io.StringIO()
            fields = sorted({key for case in report["cases"] for key in case})
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(report["cases"])
            content, media = output.getvalue(), "text/csv"
        return Response(content, media_type=media,
                        headers={"Content-Disposition": f'attachment; filename="{run_id}.{format}"'})
    @api.exception_handler(BudgetExceeded)
    async def budget_error(request, exc):
        return Response("Daily model budget exhausted", status_code=429)

    class LoginRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")
        username: str = Field(min_length=1, max_length=80)
        password: str = Field(min_length=1, max_length=256)

    @api.post("/auth/login")
    def login(body: LoginRequest, request: Request):
        if config.deployment != "hosted":
            raise HTTPException(404)
        auth = request.app.state.auth
        # Global and account-specific persistent limits cannot be bypassed with rotating IPs.
        if not auth.rate("login:global", 30) or not auth.rate("login:" + body.username.lower(), 5):
            raise HTTPException(429, "Too many login attempts")
        session = auth.login(body.username, body.password)
        if not session:
            raise HTTPException(401, "Invalid credentials")
        token, csrf = session
        response = Response(json.dumps({"username": body.username}), media_type="application/json")
        response.set_cookie(COOKIE, token, secure=True, httponly=True, samesite="strict",
                            max_age=config.session_hours * 3600, path="/")
        response.set_cookie(CSRF_COOKIE, csrf, secure=True, httponly=False, samesite="strict",
                            max_age=config.session_hours * 3600, path="/")
        return response

    @api.post("/auth/logout")
    def logout(request: Request):
        request.app.state.auth.logout(request.cookies.get(COOKIE, ""))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="strict")
        response.delete_cookie(CSRF_COOKIE, secure=True, samesite="strict")
        return response

    @api.get("/auth/me")
    def me(request: Request):
        return {"username": request.state.actor, "deployment": config.deployment}

    web = Path(__file__).resolve().parent / "web"
    @api.exception_handler(StarletteHTTPException)
    async def browser_error(request, exc):
        if exc.status_code == 404 and "text/html" in request.headers.get("accept", "") and not request.url.path.startswith(("/v1/", "/auth/", "/assets/")):
            return FileResponse(web / "404.html", status_code=404)
        return await http_exception_handler(request, exc)

    api.mount("/assets", StaticFiles(directory=web), name="assets")

    @api.get("/")
    def home():
        return FileResponse(web / "index.html")

    return api


app = create_app()
