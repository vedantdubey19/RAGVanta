import hashlib
import json
import time
import uuid
from app.ingestion import extract, chunk_pages
from app.models import Model
from app.retrieval import Retriever
from app.security import inspect, validate_output, reject_credentials
from app.storage import Store


class Laboratory:
    def __init__(self, settings):
        self.settings = settings
        self.store = Store(settings.data_dir)
        self.store.cleanup(settings.retention_days)
        self.model = Model(settings)
        self.model.budget_store = self.store
        self.retriever = Retriever(settings, self.store)

    def authorize(self, collection_id):
        if not self.store.query("SELECT id FROM collections WHERE id=? AND owner=?",
                                (collection_id, self.settings.actor_id)):
            self.store.event("collection_access", "denied", {"collection_id": collection_id})
            raise PermissionError("Collection unavailable")

    def create_collection(self, name):
        cid = uuid.uuid4().hex
        with self.store.connect() as db:
            count = db.execute("SELECT COUNT(*) FROM collections WHERE owner=?", (self.settings.actor_id,)).fetchone()[0]
            if count >= self.settings.max_collections:
                raise OverflowError("Collection quota reached")
            db.execute("INSERT INTO collections VALUES(?,?,?)", (cid, self.settings.actor_id, name))
        return {"id": cid, "name": name}

    def delete_collection(self, collection_id):
        with self.store.connect() as db:
            if not db.execute("SELECT id FROM collections WHERE id=? AND owner=?",
                              (collection_id, self.settings.actor_id)).fetchone():
                raise PermissionError("Collection unavailable")
            ids = [row["id"] for row in db.execute(
                "SELECT id FROM chunks WHERE collection_id=?", (collection_id,))]
            self.retriever.delete(ids, db=db)
            db.execute("DELETE FROM chunks WHERE collection_id=?", (collection_id,))
            db.execute("DELETE FROM documents WHERE collection_id=?", (collection_id,))
            db.execute("DELETE FROM collections WHERE id=? AND owner=?",
                       (collection_id, self.settings.actor_id))
        self.store.event("collection_deleted", "accepted", {"collection_id": collection_id,
                                                           "actor_id": self.settings.actor_id})

    def for_actor(self, actor):
        import copy
        instance = copy.copy(self)
        instance.settings = self.settings.model_copy(update={"actor_id": actor})
        instance.model = copy.copy(self.model)
        instance.model.settings = instance.settings
        return instance

    def ingest(self, data, filename, collection_id):
        self.authorize(collection_id)
        pages = extract(data, filename, self.settings)
        reject_credentials("\n".join(text for _, text in pages))
        did = uuid.uuid4().hex
        chunks = chunk_pages(pages, did, self.settings.chunk_size, self.settings.chunk_overlap)
        digest = hashlib.sha256(data).hexdigest()
        with self.store.connect() as db:
            # Extraction may outlive a concurrent collection deletion.
            if not db.execute("SELECT id FROM collections WHERE id=? AND owner=?",
                              (collection_id, self.settings.actor_id)).fetchone():
                raise PermissionError("Collection unavailable")
            used = db.execute("SELECT COALESCE(SUM(length(chunks.text)),0) FROM chunks JOIN collections "
                              "ON collections.id=chunks.collection_id WHERE collections.owner=?",
                              (self.settings.actor_id,)).fetchone()[0]
            if used + sum(len(c["text"]) for c in chunks) > self.settings.max_user_text_chars:
                raise OverflowError("User text storage quota reached")
            count = db.execute("SELECT COUNT(*) FROM documents WHERE collection_id=?",
                               (collection_id,)).fetchone()[0]
            if count >= self.settings.max_files:
                raise OverflowError("Collection file quota reached")
            db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
                       (did, collection_id, filename, digest, time.time(), len(pages),
                        json.dumps({"chunk_size": self.settings.chunk_size,
                                    "overlap": self.settings.chunk_overlap})))
            db.executemany("INSERT INTO chunks VALUES(?,?,?,?,?,?,?)",
                [(c["id"], did, collection_id, c["page"], c["start"], c["end"], c["text"])
                 for c in chunks])
            self.retriever.index([dict(c, collection_id=collection_id, owner=self.settings.actor_id)
                                  for c in chunks], db=db)
        self.store.event("ingestion", "accepted", {"document_id": did, "sha256": digest})
        return {"id": did, "sha256": digest, "pages": len(pages), "chunks": len(chunks),
                "status": "ready", "filename": filename}

    def answer(self, question, collection_id, mode="protected", top_k=3, internal=False):
        start = time.perf_counter()
        self.authorize(collection_id)
        reject_credentials(question)
        retrieved = self.retriever.retrieve(question, collection_id, self.settings.actor_id, top_k)
        decisions = [{"chunk_id": c["id"], **inspect(c["text"])} for c in retrieved]
        included = [c for c, d in zip(retrieved, decisions)
                    if mode == "baseline" or d["decision"] != "quarantine"]
        generated = self.model.generate(question, included, mode) if included else {
            "text": "Insufficient evidence.", "input_tokens": None, "output_tokens": None}
        reasons, cited = validate_output(generated["text"], included)
        blocked = mode == "protected" and bool(reasons)
        trace_id = uuid.uuid4().hex
        result = {"answer": "Answer blocked by output validation." if blocked else generated["text"],
                  "citations": [{"chunk_id": c["id"], "document_id": c["document_id"],
                                 "page": c["page"], "filename": c["filename"]}
                                for c in included if c["id"] in cited and not blocked],
                  "trace_id": trace_id, "blocked": blocked, "output_reasons": reasons,
                  "retrieved": [{"chunk_id": c["id"], "score": c["score"]} for c in retrieved],
                  "included_ids": [c["id"] for c in included], "decisions": decisions,
                  "model": self.settings.model, "provider": self.settings.provider,
                  "model_version": generated.get("model_version"),
                  "retrieval": self.settings.retrieval, "mode": mode,
                  "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                  "input_tokens": generated["input_tokens"], "output_tokens": generated["output_tokens"]}
        self.store.event("answer", "blocked" if blocked else "completed",
                         {"trace_id": trace_id, "actor_id": self.settings.actor_id,
                          "included_ids": result["included_ids"], "decisions": decisions,
                          "output_reasons": reasons, "detector_version": "patterns-v2"})
        if internal:
            result["raw_answer"] = generated["text"]
        return result
