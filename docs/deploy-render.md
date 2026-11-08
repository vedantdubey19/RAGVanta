# Deploy RAGVanta on Render

## What this deployment runs

One Docker web service hosts the same-origin HTML/JavaScript interface and FastAPI API. Streamlit remains a local developer interface; do not publish it. Render terminates HTTPS. Individual accounts, revocable secure cookies, CSRF validation and server-derived ownership protect all data endpoints. No public registration exists.

The default Render configuration runs offline extraction and lexical retrieval without external model charges. It is an operational demonstration, not an LLM security benchmark. Configure Gemini only after setting provider billing limits and approving the synthetic data sent to it.

## Deployment inputs

1. A private GitHub repository containing this source.
2. A Render account connected to that repository.
3. A paid disk-capable web-service plan and 1 GB persistent disk. Review Render's Blueprint cost preview before provisioning. Free instances cannot retain this SQLite state across restarts and are not a suitable durable deployment for this configuration.
4. Set `RAGVANTA_PUBLIC_URL` to the exact HTTPS origin you reserve in Render, for example `https://your-unique-ragvanta-name.onrender.com`. Choose the service name first, then set this value to the assigned URL. Do not include a trailing path. If Render assigns a suffix, update this environment value and redeploy before signing in.

Import `render.yaml` through Render → New → Blueprint → select repository. Review the paid plan/disk and environment fields, then deploy. `autoDeployTrigger: off` prevents unattended code publication; deploy tested commits manually.

If you create a service manually instead, select Docker, use the repository Dockerfile, set Docker command `python -m scripts.start`, mount a persistent disk at `/workspace/.runtime`, and copy the environment values from `render.yaml`. Health path: `/health`. One instance only; the app is intentionally single-process with an embedded database/index.

## Provision the first user

After deployment, open the service's Render Shell and run:

```bash
python -m scripts.manage_users create your-username
```

Enter and confirm a unique password privately at the prompt (minimum 14 characters). The script never takes a password on the command line. There are no default accounts or bootstrap passwords. Open the service HTTPS URL and sign in. Create a collection and upload only synthetic test documents.

For additional accounts, repeat the command. Disable an account with `python -m scripts.manage_users disable username`. Reset a password with `python -m scripts.manage_users reset-password username`; this revokes all existing sessions for that user. Account lifecycle changes require Render administrative access, not a browser role.

## Model configuration and budget

To enable Gemini, set `RAGVANTA_PROVIDER=gemini`, `RAGVANTA_MODEL=<available model ID>`, and secret `RAGVANTA_GEMINI_API_KEY` in Render's environment settings. Never put the value into source, a screenshot, an uploaded document or a chat. The app enforces global/user daily attempted-call ceilings (including retries), concurrency 2, prompt-size and output limits. Set an independent provider-side monetary budget; request ceilings bound calls, not exact currency cost. Ollama requires a separately secured operator-managed endpoint and is not bundled on Render.

The default image omits heavy semantic dependencies. Keep `RAGVANTA_RETRIEVAL=lexical` on the smallest plan. A semantic deployment needs a custom image with `--extra semantic`, preloaded model cache, adequate RAM, and a separate live validation run; do not turn it on merely by changing the environment.

## Security and operations

- HTTPS is supplied by Render. Host validation requires the exact configured origin; mutation requests require that origin plus the session CSRF token. No permissive CORS is configured.
- Session cookies are Secure, HttpOnly, SameSite=Strict, with an 8-hour default expiry; only token digests are stored. Disabling/resetting a user revokes sessions. Responses include CSP, HSTS, no-sniff, no-referrer and anti-framing headers.
- Rates: 30 authenticated requests/minute/user; login limits apply both globally and per account. Upload, collection, total text-storage and retained-run quotas apply on the server. The one-instance requirement is mandatory.
- Linux PDF subprocesses have CPU/address-space limits and a 10-second wall timeout. The container runs as a non-root user. No model execution tools exist.
- Experiments run in a single background worker. Poll saved runs for progress; restarted queued/running runs become `interrupted`. Progress survives disconnects, but incomplete runs are not automatically resumed.
- Cleanup runs hourly and at startup; expired runs/audit events and isolated experiment corpora are removed. Operator documents remain until deliberately removed under the owner's policy. Synthetic-only remains required.
- Read `/health` with an uptime monitor. It is unauthenticated and reveals no provider keys or internal settings. Render uses the same path for service health/restarts. Review audit events through restricted administrator SQL/shell access; do not grant ordinary visitors shell access.
- Render disks have platform snapshots. For database-consistent off-host backups, run `python -m scripts.backup /path/on/encrypted/storage/backup.sqlite3`, then copy the file to your approved encrypted backup service. Keep backups 7 days and test a restore monthly. The SQLite backup contains users, documents, run reports and audit records. Embedding caches are derived and rebuilt from canonical chunks; isolated experiment databases may be archived separately when needed for exact trace reproduction.
- Do not configure a second instance, public Streamlit, additional untrusted origins, arbitrary model URLs, or a proxy that bypasses authentication.

## Before treating the service as operational

Verify anonymous data routes return 401; two accounts cannot access each other's collections, chunks, reports or runs; login/logout work over HTTPS; a synthetic PDF can be uploaded and cited; an experiment completes and exports; budget/size caps reject excess requests; disable-user revokes a session; and a backup can be restored. Record the actual deployment URL and commit SHA. Local tests are not a substitute for these hosted checks.

For suspected compromise, follow [incident-response.md](incident-response.md). Report security issues privately to the operator who provisioned the account using your established contact channel; do not post documents, sessions or keys in public issues.

References: [Render Blueprints](https://render.com/docs/blueprint-spec), [persistent disks](https://render.com/docs/disks), [free-tier limitations](https://render.com/docs/free), [HTTPS handling](https://render.com/docs/web-services).
