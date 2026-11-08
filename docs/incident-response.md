# Abuse reporting and incident response

This is an invite-only synthetic-data laboratory. The deployment administrator is the incident owner. Report suspected leakage, account misuse, unexpected costs or unsafe uploads directly through the private channel used to provision your account. The operator must provide this contact to every invited user before granting access. A public self-service registration or support mailbox is not part of this application.

1. Contain: suspend the Render service or disable the affected account using the administrator CLI. Do not weaken authentication to debug an incident. Stop ongoing model usage at the provider if a cost spike is suspected.
2. Revoke: disable accounts/reset passwords to revoke server-side sessions. Rotate exposed provider credentials in the provider console, then update Render secrets. Never paste secrets into reports or logs.
3. Preserve: copy access-controlled audit metadata and relevant run IDs before cleanup. Do not publish raw document text, passwords or session tokens. Identify the deployed commit and exact time window.
4. Assess: check collection ownership, model-usage counters, unauthorized requests, experiment statuses, upload hashes and data sent to providers. Treat plausible citations as insufficient evidence of a correct or authorized answer.
5. Recover: patch and test the cause, restore a verified backup if required, redeploy a known commit, provision fresh credentials, and recheck anonymous/cross-user access. Validate a restore in isolation first; invalidate restored sessions before reopening access.
6. Notify: tell affected invited users what data and dates are involved through the established private channel. Record what is known, unknown, remediated and still at risk. Do not claim a security guarantee.
7. Review: add a regression test, update the threat model, review provider budgets and permissions, and document a closure decision by the deployment administrator.

Restore procedure: stop all writers, preserve the current database privately, replace the canonical SQLite database from the validated backup (remove stale WAL/SHM files while no process is running), revoke every restored session, and restart one instance. Canonical document text rebuilds semantic indexes on startup; isolated experiment data must be restored separately if required. Follow the data owner's deletion/notification obligations if real material was uploaded contrary to the synthetic-only policy.
