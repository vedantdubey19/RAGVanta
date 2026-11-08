# Implementation status

The original planning sections remain in the architecture/design/security/limits documents, followed by dated implementation updates. The release implements an offline-capable workbench and a separate hosted profile prepared for Render; it does not claim a deployed public service.

FastAPI serves both the same-origin hosted HTML/JS/CSS interface and API. Streamlit is local-only. SQLite stores accounts, session digests, usage/rate counters, canonical chunks, provenance, runs, redacted audit events and optional normalized embedding vectors. Sentence Transformers is an optional semantic encoder with pinned model revision and remote-code loading disabled. ChromaDB was removed after audit findings; the original planned stack has been revised accordingly.

Uploads retain extracted text, document hashes and offsets rather than original bytes. Owner-scoped deletion exists. PDF extraction is a resource-bounded, environment-sanitized subprocess; it still shares the container's OS trust boundary. No OCR, arbitrary model tools, third-party targeting, or open registration exists.

Hosted data access uses server-derived account identity. Sessions are hashed and revocable; login uses scrypt and bounded computation. Origin/CSRF/Host checks, browser headers, quotas, hourly cleanup and persistent attempted-call budgets are implemented. One asynchronous experiment worker shares the provider semaphore and root budget database with chat. Startup marks queued/running work interrupted. This is intentionally a single-instance system, not a horizontally scaled SaaS.

The evaluator preserves identical paired corpora/models/settings except selected defenses, records inclusion separately from retrieval and raw/displayed failures, and exports category/language breakdowns, prompt hashes, defense decisions, settings and dataset/corpus hashes. Provider model version is retained when exposed. Failed and unattempted cases remain incomplete. Held-out examples are separately authored but small/public; no detector was tuned to their outcomes.

Read [verification.md](verification.md) for measured checks and unresolved external validation, [deploy-render.md](deploy-render.md) for hosting/account/budget/backup setup, and [incident-response.md](incident-response.md) for abuse and recovery procedures. Pattern detectors and citation-ID checking do not guarantee semantic correctness or injection resistance.
