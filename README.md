# ◈ RAGVanta

**Adversarial RAG Security & Evaluation Platform**
Test the threats. Protect the intelligence.

A Python workbench for cited document Q&A, controlled synthetic prompt-injection experiments, layered defenses, and security/utility comparisons. Supports a local developer workflow and an invite-only hosted profile prepared for Render.

## Run locally

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen --extra dev
cp .env.example .env
uv run python -m scripts.seed_demo
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Open [the web workspace](http://127.0.0.1:8000) or [interactive API docs](http://127.0.0.1:8000/docs). The default local profile is restricted to loopback and uses the local operator identity. Optional local `RAGVANTA_API_TOKEN` requires a configured client, such as Streamlit; the browser workspace uses session authentication in hosted mode.

For the original local Streamlit interface, run in a second terminal:

```bash
uv run streamlit run dashboard/streamlit_app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Open [Streamlit](http://127.0.0.1:8501). Do not expose Streamlit publicly. The hosted web client and API share one origin and one process.

## Render deployment

The complete deployment recipe is [docs/deploy-render.md](docs/deploy-render.md). `render.yaml` defines a Docker web service, one instance, a 1 GB persistent disk, explicit hosted mode, a health check and request budgets. **These are deployment files; no hosted deployment or live URL is implied.**

The SQLite design needs a paid disk-capable Render plan. Review the platform cost preview before provisioning. Configure the exact HTTPS public origin, then create the first account privately in Render Shell with `python -m scripts.manage_users create username`. There are no default passwords or public registration. Render supplies HTTPS and platform secret storage. Live-host validation, provider-side budgets, administrator contacts and backups remain operator tasks.

## Features

- Bounded UTF-8 TXT/PDF ingestion with hashes, page/character provenance, deterministic chunking, previews and owner-scoped deletion.
- Collection-scoped retrieval before generation; cited answers, decision traces, baseline/protected modes, insufficient-evidence behavior.
- Unicode-normalized heuristic inspection, quarantine, evidence-separated prompts, canary/citation/link output checks and high-confidence credential rejection.
- 30 development attacks + 30 benign questions, plus a separately authored held-out set of 10 attacks + 10 benign questions. Long-context held-out fixtures include target chunks beyond the first chunk. The held-out set remains small and public, not proof of generalization.
- Paired experiments against isolated corpora; separate retrieval/inclusion/obedience outcomes, raw and displayed failure metrics, benign utility and false blocks, exact denominators, category/language breakdowns, prompt hashes and enabled defense configuration.
- Hosted asynchronous execution, persisted per-case progress, interrupted-run detection, completed-run deletion, JSON/CSV exports, hourly/startup retention cleanup.
- SQLite canonical storage and optional SQLite embedding vectors. Derived indexes are checked against authorized canonical rows before evidence reaches the model.

## Providers and retrieval

Default `extractive-v1` + `lexical` runs without credentials or downloads. It selects matching source sentences and cites them. It is not an LLM; marker-copying smoke experiments do not establish instruction-following or LLM robustness. No invented performance numbers are shown.

Gemini: set `RAGVANTA_PROVIDER=gemini`, `RAGVANTA_MODEL=<available model ID>` and `RAGVANTA_GEMINI_API_KEY=<key>` in the local `.env` or Render secret environment. Verify access/billing with the provider. Never send real credentials or customer data. Model IDs/endpoints are server settings, not request parameters.

Ollama: start an operator-managed server, set `RAGVANTA_PROVIDER=ollama` and `RAGVANTA_MODEL=<installed model>`. The default endpoint is `http://127.0.0.1:11434`; a hosted instance needs a separately secured reachable server. No Ollama model is bundled.

Sentence Transformers + SQLite vector cache:

```bash
uv sync --frozen --extra dev --extra semantic
```

Set `RAGVANTA_RETRIEVAL=semantic`. First use downloads the pinned revision of `sentence-transformers/all-MiniLM-L6-v2`. Verify the optional path with `uv run --extra semantic python -m scripts.check_semantic`. The minimal Render image deliberately excludes these heavy extras; a semantic host needs an image built with the semantic extra, preloaded caches and adequate memory. Do not enable it on an undersized plan.

## Hosted security controls

Individual administrator-provisioned accounts use scrypt password hashes, bounded password verification, hashed opaque sessions, secure host-only HttpOnly cookies, expiry and revocation. Mutations require the configured origin and session CSRF token. Host allowlisting, strict same-site cookies, no permissive CORS, CSP, HSTS, no-sniff, no-referrer and anti-framing headers support the browser boundary. All collection, document, chunk, chat, experiment and report permissions derive from the session identity.

Server-enforced quotas cover files, collections, total stored text, retained runs, rates and attempted provider calls. Persistent daily user/global request reservations include retries. One shared model semaphore bounds requests across chat and experiments. Request ceilings are not currency budgets; configure a separate provider billing limit.

PDF extraction uses an environment-sanitized child process with a 10-second wall deadline and, on Linux, CPU/address-space limits. The container runs non-root. No model-triggered execution, network tools, messaging or third-party targets exist. Native parser compromise remains a risk within the container boundary; this is not a general hostile-file sandbox.

## Reproduce offline experiments

```bash
uv run python -m scripts.benchmark --split development --limit 50 --output results/development.json
uv run python -m scripts.benchmark --split development --offset 50 --limit 10 --output results/development-tail.json
uv run python -m scripts.benchmark --split held_out --limit 20 --output results/held-out.json
```

Each scenario runs once per mode. These three batches exercise all 80 scenarios / 160 cases while keeping each batch at or below 50 scenarios. Baseline retains access controls and budgets. Both modes use the same corpus/model/retrieval settings; selected experimental defenses differ. Marker/reference substring scoring needs manual audit for semantic conclusions. Provider/model comparisons must be reported separately from defense-effect comparisons.

Conditional attack success uses cases with target evidence included in context. No included targets means `null` / “Not exercised.” Failed and unattempted cases remain incomplete, never counted as safe. Restarted hosted runs are marked interrupted and require an explicit new run.

## Verify

```bash
uv run ruff check .
uv run pytest -q
uv run python scripts/check_release.py
uv run pip-audit --local
```

Tests exercise the API and Streamlit components without live model charges, including two-account access isolation, CSRF/origin/Host validation, login limits, cookie properties/revocation, upload constraints, PDF parsing, quotas, credential rejection, scoring, incomplete cases, report exports and provider contracts. See [verification.md](docs/verification.md) for actual results and limits; local tests do not substitute for a hosted penetration test.

CI runs lint/tests/release invariants, dependency auditing, container building and secret scanning. `uv.lock` freezes dependencies; the base container image is pinned by digest. `.env`, runtime databases, caches and local reports stay out of Git and images.

## Budgets and retention

Defaults: 10 MB/file, 50 PDF pages, 100 files/collection, 250,000 extracted characters/file, 2,000 characters/question, top 3 chunks (max 5), 1,024 output tokens, 30-second per-attempt provider timeout, at most 2 retries, 2 concurrent model calls, 30 API requests/minute/account, 10 collections/account, 5,000,000 stored chunk characters/account and 100 retained runs/account. Daily attempted model-call caps are 200/account and 1,000 globally.

Run/audit/isolated-fixture retention defaults to 30 days; hosted cleanup runs hourly and at startup. `uv run python -m scripts.cleanup` can trigger cleanup manually. Original upload bytes are discarded after hashing/parsing; extracted document text is retained until owner deletion. Database and directory permissions are restricted. Use approved encrypted backup storage and follow [incident-response.md](docs/incident-response.md). Backups contain private account/document metadata and need their own retention controls.

The supported deployment has one process/instance with bounded background execution and embedded storage. A horizontally scaled SaaS needs a different database/job-queue/limiter design.

## Containers

```bash
cp .env.example .env
docker compose up --build
```

The local Compose setup includes Streamlit and uses Linux host networking (Docker Desktop requires host networking enabled). Render uses the lean Docker image and hosted command in `render.yaml`; it does not use Compose. No secrets are copied into either image.

## Documentation

[Recovered context](docs/project-context.md) · [Architecture](docs/architecture.md) · [Design](docs/design.md) · [Security model](docs/security.md) · [Limits](docs/rulesandlimits.md) · [Implementation notes](docs/implementation.md) · [Render runbook](docs/deploy-render.md) · [Incident response](docs/incident-response.md) · [Verification](docs/verification.md)

Guardrails can miss attacks and reject useful evidence. Valid citation IDs do not prove factual entailment. No real-world security effectiveness, perfect privacy detection or universal prompt-injection protection is claimed.
