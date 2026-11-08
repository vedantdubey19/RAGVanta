# Verification record — 7 November 2026

No Render resources were created, no paid deployment was approved, and no source was pushed to GitHub: the user selected deployment files only. A local Git index exists for source selection and secret scanning.

## Completed checks

- Isolated Python 3.11 environment and frozen `uv.lock` dependencies.
- 49 automated tests pass: local API/Streamlit behavior; hosted two-user isolation across documents/chunks/chat/runs/reports; session security, logout/revocation, CSRF/Origin/Host checks; authentication limits; uploads and Linux-compatible PDF constraints; storage/model budgets; credential rejection; incomplete/unattempted accounting; exports and provider contracts.
- Ruff, JavaScript syntax check, Render YAML parsing, and release invariants pass.
- Lean Docker image builds with a digest-pinned Python base and pinned uv installer. Its Linux non-root smoke test passed under a 512 MB container limit, one CPU, PID limit, dropped capabilities and no-new-privileges: login, CSRF, private data rejection, 192 MB PDF worker cap, cited Q&A, response headers and logout.
- Optional Sentence Transformers integration passed with real downloaded `all-MiniLM-L6-v2` weights: persisted SQLite embeddings, retrieval/citations and two-user isolation. Model revision is pinned in configuration. This test uses offline extraction, not a live generative model.
- Full installed dependency audit, including the optional semantic stack, reports zero known vulnerabilities after removing ChromaDB. A prior audit flagged unresolved Chroma advisories; no exceptions were added to suppress them. The current audit result is `results/dependency-audit-final.json` (local/ignored).
- Gitleaks source-only redacted scan passed on the selected source files. Runtime databases, model caches, environment files and third-party packages are not deployment source.
- Offline v2 benchmark: all 80 scenarios × two modes = 160 completed cases, batched 50 + 10 development scenarios and 20 held-out scenarios. [Measured summary](benchmark-summary.json) contains denominators and caveats.

## Actual smoke measurements

Development: 30 attacks + 30 benign questions. Baseline copied synthetic markers in 15/30 attack outputs; protected mode quarantined all 30 target chunks, with zero displayed markers. Both modes passed all 30 benign reference checks. Protected conditional susceptibility is not exercised because no target reached generation.

Separately authored held-out cases: baseline copied markers in 6/10 attacks; protected copied markers in 4/10. Protected mode passed 6/10 benign reference checks and falsely blocked 4/10. These results deliberately retain weaknesses and false positives; the detector was not tuned to the held-out outcomes.

**These are extractor/pipeline measurements, not live LLM attack-success evidence.** Marker copying by a sentence extractor does not establish instruction following. The small public held-out set is more varied than the development generator, but is not a comprehensive independent security benchmark.

## Remaining external verification

No live Gemini/Ollama model generation, Render build/deployment, public HTTPS session, production backup service, hosted uptime monitor, or public visual-browser QA was verified. Browser access for earlier local visual inspection was declined; backend checks and local Streamlit component tests were used. Deployment files and an operator runbook are present, but the service must undergo the hosted checks in [deploy-render.md](deploy-render.md) after the operator chooses to deploy.

Dependency/secret scans are point-in-time checks, not proof of universal safety. Platform administration, provider-side monetary limits, encrypted off-host backups, tested restoration and private incident contact remain operator responsibilities. The invited-user deployment is single-process/instance and synthetic-only.
