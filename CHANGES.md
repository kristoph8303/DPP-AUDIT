# Changes in 1.1.0-candidate (response to the break-it review)

This file records the candidate's intended changes and the upstream author's
test mapping. It is not a claim that this copied package has been rerun in the
current assembly. See `TEST_RESULTS.txt` for this copy's status and
`docs/LIMITATIONS.md` for unresolved assurance gaps.

Unchanged rules: statuses (APPROVED / REJECTED / REVIEW_REQUIRED / INDETERMINATE), strict traceability, AI
assessments can never be accepted, an empty allowlist fails closed, mandatory-rule aggregation, retired/future
policies can still be evaluated historically, and all 21 original tests pass unmodified except the one that
asserted the broken `******` header (it now asserts `Bearer <key>`).

| ID | Fix |
|---|---|
| C1 | Header is `Authorization: Bearer <key>`; test no longer asserts the broken value. |
| C2 | Runs record `publication_eligibility` (also in trail and every export). Draft policies cannot be APPROVED (downgraded to REVIEW_REQUIRED) — new rule. Retired/not-yet-effective keep their historical result. |
| C3 | All accepted assessments per evidence are considered; contradicted/outdated/expert-review or conflicting verdicts give REVIEW_REQUIRED regardless of order. |
| C4 | New `ReviewDecision` record (authorized, optionally signed) can approve or reject a manual-review rule; without one the rule still requires review. |
| C5 | Fingerprint now covers the assessor allowlist, key-holder IDs, signature mode and review decisions; `compute_input_fingerprint()` recomputes it; allowlist hash is in every export. |
| C6 | Every ignored assessment/decision is logged with a reason; future-dated and timezone-naive assessments are refused. |
| C7 | With `maximum_age_days`, both retrieval and `published_date` must be within the limit; a missing `published_date` does not count. |
| C8 | IDs limited to `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`; reports/CSV strip control characters; CSV cells starting `= + - @` are escaped; exports are written atomically. |
| C9 | The model's answer is no longer attached to URLs as a "snippet". |
| C10 | All network/decoding errors wrapped in `ProviderError`; retries (default 2) for 429/5xx/timeouts honoring `Retry-After` (capped 30 s); 2 MB response cap. |
| C11 | `expected_result` is enforced (None = True; False inverts); must be a boolean. |
| C12 | Type-strict comparisons (`True != 1`), ordered operators need comparable types, `IN` needs a list, `EXISTS` needs a boolean, dotted literal keys resolve, reasons truncate long values. |
| C13 | `run_safe()` returns an INDETERMINATE record with the error; sets/bytes in input are supported; unsupported types/NaN/non-string keys fail clearly before any decision. `run()` still raises as before. |
| C14 | https only; localhost, private/link-local/reserved IPs, internal suffixes, ambiguous numeric hosts and credentials rejected; URLs normalized and de-duplicated. |
| R1 | Optional HMAC signatures for assessments and decisions (`require_signatures=True` makes them mandatory); `collected_by` blocks self-assessment. |
| R2 | `Rule.claim_text_field` + `claim_text_sha256` bind evidence/assessments to exact claim wording. |
| R3 | `minimum_count` counts distinct normalized sources. |
| R4 | `Assessment.evidence_sha256` attests to the exact evidence record; later edits void the assessment. |
| R5 | `EvidenceRecord.requirement_ids` scopes evidence to requirements (empty = any). |
| R6 | Non-mandatory rules that are not PASS appear in `warnings` (status rule unchanged). |
| R7 | Caveat added to JSON, CSV and the first lines of the human report and demo. |
| R8 | Query capped at 500 chars, control characters removed, system prompt tells the model to treat the query as data. Sending text to Perplexity is still disclosure to a third party. |
| R9 | `search_results` (titles/snippets) parsed defensively; the provider format was NOT verified against live documentation. |

## Not solved (needs process or deployment, not code)
- Signing keys, the allowlist and policies must come from trusted configuration; the engine cannot protect against a compromised backend.
- Source authenticity and whether a passage truly supports a claim still need human/expert review.
- `quality_score` and `source_type` remain assertions by whoever creates the record; R4 only ensures an assessor attested to the exact values.
- DNS rebinding: URL checks are textual; any code that fetches a candidate URL must re-check the resolved IP.
- Live Perplexity behavior (auth, rate limits, response format) has not been exercised.
