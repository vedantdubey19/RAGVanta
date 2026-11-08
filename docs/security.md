# RAGVanta — Security Model & Controls

**Classification:** Defensive testing design
**Version:** 1.0
**Scope:** Controlled testing of RAGVanta and other systems the operator explicitly owns or is authorized to test.

## 1. Security objectives

1. Keep untrusted retrieved content from becoming authoritative instructions.
2. Ensure no cross-collection or cross-user content reaches retrieval context.
3. Prevent disclosure of private data through generated answers, logs or reports.
4. Limit any model-triggered side effect; v1 model has **no execution or external-action tools**.
5. Produce honest measurements of residual risk, including guardrail false positives.

**Explicit non-guarantee:** Prompt injection cannot be eliminated by a single system prompt, delimiter, regex filter, or output checker. RAGVanta evaluates risk reduction, not invulnerability.

## 2. Assets and trust boundaries

| Asset | Risk | Protection |
|---|---|---|
| API keys / provider credentials | Accidental exposure | Environment secrets; never prompt, log, or commit |
| Authorized document text | Cross-tenant leakage | Authenticated collection-scoped retrieval and document metadata enforcement |
| Synthetic canary markers | Test disclosure | Fake-only values, restricted report rendering, deterministic test checks |
| RAG system prompt | Instruction hijack | Fixed server-controlled policy, no concatenated untrusted role blocks |
| Vector index | Unauthorized chunks | Trusted metadata, explicit owner filter, access tests |
| Run logs / traces | Data leakage | Minimize, redact, restrict retention/access |
| Evaluation integrity | Misleading claims | Fixed datasets, hashes, audited denominators, baseline parity |

Trust levels: **server configuration (trusted)**; **authorized operator request (validated but untrusted text)**; **uploaded documents and retrieval chunks (untrusted evidence)**; **model response (untrusted output)**.

## 3. Threat model

### Actors
- Authorized developer using the laboratory correctly.
- Malicious document author whose text appears in a retrieved chunk.
- Unauthorized user attempting to access another collection (future hosted mode).
- Accidental operator error (committed key, public logs, mislabeled result).

### Entry points
- PDF and text uploads.
- Retrieved vector-store chunks.
- Question and collection identifiers submitted to API.
- Configuration files, report export paths, and third-party model API.

### Threat categories

| Threat | Example in our synthetic sandbox | Main defenses |
|---|---|---|
| Instruction override | Retrieved note tells assistant to ignore its task | Lower-trust evidence handling; adversarial evaluation |
| Role/system spoofing | Document contains fake `system:` heading | Reject role escalation; prompt structure; detection |
| Answer contamination | Document tries to force a false policy answer | Citation checking, evaluation, provenance review |
| Synthetic secret exfiltration | Document asks for fake canary to appear in answer | No actual secrets in context; output checks; test canaries |
| Cross-collection leakage | Search query targets unrelated demo collection | Authorization before retrieval, server-assigned metadata |
| Encoded/obfuscated injection | Suspicious instruction encoded or paraphrased | Layered inspection and tests; no regex-only promises |
| Log or report exposure | Trace contains secret or user document | Redaction, retention and access controls |
| Denial of service / excess spending | Repeated huge inputs or test runs | Size limits, timeouts, concurrency and token budgets |

## 4. Preventive controls

### 4.1 Retrieval authorization (highest priority)
- Resolve actor identity on server; never trust `owner_id` supplied by client.
- Authorize requested collection **before vector search**.
- Scope every query using trusted metadata (`collection_id`, `owner_id`) and verify returned document ownership again.
- Never rely on an LLM to decide whether retrieved material is authorized.
- Test that unauthorized chunks are absent from the model context, even when semantically relevant.

### 4.2 Prompt and document separation
- Set fixed task instructions in system/developer messages controlled by the application.
- Pass retrieved chunks in clearly labeled, quoted evidence blocks with immutable chunk IDs.
- State that source content can be cited or summarized but must never override application instructions.
- Do not treat XML tags, quotation marks, or spotlighting alone as a complete security boundary.
- Never place real keys or protected account records into the model prompt.

### 4.3 Retrieved-content inspection
- Scan chunks for suspicious role indicators, instruction overrides, data extraction directives and obfuscation patterns.
- Classify findings into `allow`, `flag`, or `quarantine` with reason codes.
- Build tests for evasions and benign false alarms; do not present keyword matching as sufficient defense.
- If a needed chunk is quarantined, answer from remaining evidence or state that evidence is insufficient; don't silently hallucinate.

### 4.4 Output checks
- Search for synthetic test canaries and known prohibited formats.
- Validate citation IDs against chunks actually included in the prompt.
- Constrain output length and outbound links in the demo.
- Treat a blocked output as a signal for investigation; preventing the final string does **not** prove underlying access was safe.

### 4.5 Tool / action restrictions
- v1 has read-only retrieval and generation; **no shell, network browsing, messaging, file writes triggered by the model, or third-party action APIs**.
- If tools are added later, explicitly allowlist capabilities, validate arguments, scope credentials and require human approval for side-effecting actions.
- Never grant a model direct credentials to arbitrary services.

### 4.6 Files and dependencies
- Permit only small PDF/text fixtures in v1 (defaults: 10 MB per file, 50 pages per PDF, 100 files per collection; configurable downward).
- Reject encrypted/unsupported PDFs and malformed content; enforce extraction timeout/memory budget.
- Sanitize filenames, prevent path traversal, compute file hashes, and avoid executing embedded scripts.
- Pin versions for repeatable benchmarks, audit dependencies and rebuild images regularly.

## 5. Detection and response

Security events should include `trace_id`, timestamp, scenario ID (if test), source chunk IDs, detection rule/classifier version, decision and reason code. Do **not** log raw secrets, full uploaded documents or sensitive model prompts by default.

| Event | Response |
|---|---|
| Unauthorized collection request | Reject with `403`/`404`, audit event |
| Suspicious chunk | Flag/quarantine, preserve non-sensitive evidence metadata |
| Synthetic canary in output | Block displayed answer, mark attack success internally, log case ID |
| Provider timeout | Bounded retry for safe call, record failure; never infinite retry |
| Test quota exceeded | Stop run and record partial completion |
| Accidental real credential detected | Stop ingestion/test, quarantine input and rotate exposed credential through provider process |

## 6. Security experiments

Use synthetic data only. Test payloads must be confined to authorized local corpora, and the test runner should not execute arbitrary URLs or exfiltration instructions. Cases should have clear expected outcomes and code-checkable markers where possible.

### Mandatory comparison structure
- Same dataset version/hash, model identifier, corpus snapshot and retrieval configuration.
- **Baseline:** restricted only to test-safe infrastructure; disable experimental defenses but retain essential file isolation, authorization and budget limits.
- **Protected:** enable selected guardrails, record exactly which ones.
- Record whether the poisoned chunk was actually retrieved and presented to the model.
- Report attack success conditional on retrieval and end-to-end success separately.
- Use a legitimate QA benchmark to detect regressions/false blocks.
- Human-review ambiguous outcomes and publish limitations.

### Example scoring
Suppose 40 attempts were made, 30 delivered the attacker chunk to model context, and 6 of those caused the defined failure:

- Retrieval exposure: 30/40 = **75%**.
- Conditional attack success: 6/30 = **20%**.
- End-to-end success: 6/40 = **15%**.

These are illustrative numbers, not measured project results.

## 7. Secret and privacy handling

- Use `.env` locally and `.env.example` with blank values; never commit real keys.
- Prefer short-lived scoped provider credentials where supported.
- Use synthetic identities, synthetic policy documents and artificial canary values.
- If a real customer document is accidentally submitted, stop testing and follow the owner's handling/deletion requirements.
- Never ship raw protected markers or private document content in a public GitHub benchmark report.
- For external LLM APIs, check data-handling terms and obtain permission before sending any real business data. The default is synthetic-only.

## 8. Required security tests

- [ ] Unauthorized collection content cannot be retrieved, even if highest similarity.
- [ ] A document containing fake `system:` instructions cannot alter API privileges.
- [ ] Synthetic canary cannot be returned by protected mode without detection/logging.
- [ ] Legitimate questions still work when retrieved text contains benign words such as “ignore” or “system.”
- [ ] Evidence citations refer only to authorized chunks used in generation.
- [ ] Upload cannot traverse directories or execute embedded content.
- [ ] `.env`, credentials and sensitive traces are excluded from Git and Docker image.
- [ ] Rate, payload and token budgets are enforced.
- [ ] Failed/partial test runs are labeled honestly.

## 9. Remaining risks

A capable attacker can paraphrase or hide instructions, manipulate retrieval ranking or exploit model behavior not captured by the test dataset. Output filtering may miss novel leak formats; prompt labels may be ignored; local-only controls do not replace real authentication in remote deployments. Document these limitations in every release report.

## 10. Security references

- OWASP, *LLM01: Prompt Injection*: https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- OWASP, *Top 10 for LLM Applications*: https://genai.owasp.org/llm-top-10/
- Microsoft Research, *Defending Against Indirect Prompt Injection Attacks With Spotlighting*: https://arxiv.org/abs/2403.14720

See [architecture.md](architecture.md), [design.md](design.md), [rulesandlimits.md](rulesandlimits.md).

## Hosted implementation update — 7 November 2026

The invited-user hosted profile adds scrypt password verification (N=131072, r=8, p=1, bounded parallel verification), server-side hashed session tokens, secure host-only HttpOnly cookies, expiry/revocation, strict same-site policy, origin/CSRF validation, trusted Host checks, CSP and additional security headers. No public registration is exposed. Ownership derives from the authenticated session on every collection, chunk, chat, run and report operation; the local shared token is rejected in hosted mode.

Durable per-account API throttles, global/account login limits, collection/text/run quotas, and attempted model-call budgets (including retries) supplement existing payload and generation caps. Hourly/startup cleanup removes expired run metadata, audit events, sessions and isolated experiment corpora. Linux PDF workers enforce address-space/CPU limits, discard inherited secret environment values, and retain wall-clock limits; native parsing still shares the container's operating-system trust boundary and is not a general hostile-file sandbox.

Hosted experiments are asynchronous with one active run. Service restart marks unfinished runs interrupted. Baseline retains essential access and budget controls. Reports include distinct prompt hashes, enabled defenses, detector decisions, category/language breakdowns and separate raw/displayed failure metrics. A separately authored held-out set includes payloads without literal CANARY markers; no detector tuning to held-out outcomes is claimed.

The same-origin hosted interface uses text-only rendering of untrusted source/model content and external scripts/styles under CSP. Streamlit is a local development interface only. Operator-provisioned accounts, synthetic-only inputs, a single deployment instance and a protected persistent disk remain required. High-confidence credential patterns are rejected, but this is not comprehensive secret or personal-data detection.

Operational requirements are in [deploy-render.md](deploy-render.md) and [incident-response.md](incident-response.md). HTTPS, platform secret storage, backups, provider-side monetary budgets and administrator access are deployment responsibilities and must be verified on the actual host. No implementation provides universal prompt-injection immunity.

### Dependency decision: embedded vectors

The optional ChromaDB dependency was removed after `pip-audit` reported CVE-2026-45829, CVE-2026-45830 and related advisories with no patched release listed. No Chroma server had been exposed, but the release avoids carrying that dependency. Semantic retrieval now stores normalized float32 embeddings in the canonical SQLite database and performs authorized collection-scoped cosine scoring in-process. Sentence Transformers is configured with `trust_remote_code=False`. This choice fits the bounded corpus and single-instance limits; it is not a claim of large-scale vector-search performance. See the [authorization advisory](https://github.com/advisories/GHSA-2wm9-hf6c-p5cr).
