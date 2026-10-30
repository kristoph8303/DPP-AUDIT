# DPP-AUDIT — full-repository audit candidate

**Status: audit candidate, not frozen and not production-certified.** This repository combines the stricter deterministic engine candidate, compatible exports/reporting, a working synthetic demo, and a separate Perplexity source-discovery adapter.

## What it does

- Evaluates structured policy/rule/input/evidence/assessment records deterministically.
- Records an explicit evaluation date, policy/rule traceability, audit trail, and SHA-256 input fingerprint.
- Distinguishes `APPROVED`, `REJECTED`, `REVIEW_REQUIRED`, and `INDETERMINATE`.
- Exports a JSON validation record, CSV rule ledger, and human-readable report.
- Uses Perplexity only to discover **candidate sources**. Candidate results are marked `candidate_unverified`; they do not become accepted evidence or assessments automatically.
- Includes tests for the engine and adapter with a recorded provider response; tests do not require a live Perplexity API call.

## Important limits

This is not yet a complete customer-facing document-ingestion or claim-extraction service. The engine does not itself authenticate a website, verify that a passage supports a claim, prove a source is authoritative, or replace human/expert review. Quality scores and assessment records are only as trustworthy as the trusted process that creates and authorizes them. Do not treat `APPROVED` as a blanket truth guarantee.

The assessor allowlist must be controlled by trusted application configuration. Do not accept arbitrary policy, evidence, assessment, or assessor-authorization records directly from an untrusted client or AI worker.

## Run locally

Python 3.12 recommended.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python demo.py
```

The demo writes `output/validation_run.json`, `output/audit.csv`, and `output/human_report.txt`. Its data and URL are synthetic and intentionally use `example.invalid`.

## Perplexity adapter setup

Set `PERPLEXITY_API_KEY` in your local environment or deployment secret store. Do not paste the key into source code, commit it, or put it in test fixtures. The adapter reads the variable automatically:

```bash
# macOS/Linux shell example
export PERPLEXITY_API_KEY="your-key"
python -c 'from dpp_audit.perplexity_adapter import discover_sources; print(discover_sources("Find primary sources for [claim]"))'
```

The adapter calls Perplexity's chat completions endpoint. A live call incurs API use and is intentionally not part of automated tests. Every result remains an unverified candidate until a separate review/verification process records a supported assessment.

## Repository layout

- `dpp_audit/engine.py` — deterministic evaluator and exports
- `dpp_audit/perplexity_adapter.py` — isolated provider adapter and normalizer
- `tests/test_engine.py` — engine regression/adversarial tests
- `tests/test_perplexity_adapter.py` — recorded-response adapter tests
- `demo.py` — end-to-end synthetic example
- `.github/workflows/tests.yml` — CI test workflow

## Copilot / independent review request

Review and test the **entire repository as one system**, not just individual files. Try to break it. Do not make changes yet; first return findings with file/line references, reproduction steps, severity, expected behavior, actual behavior, and suggested fixes. Prioritize security/trust-boundary failures, incorrect decisions, inconsistent statuses, traceability/fingerprint weaknesses, malformed inputs, data leakage, API failures/timeouts/rate limits, and missing end-to-end coverage. Clearly separate confirmed defects from risks and recommendations. Run the test suite and demo, add adversarial tests in a separate proposed patch or branch only after reporting baseline results, and do not claim source authentication or production readiness based only on passing tests.

## Release gate

Do not tag this as `v1.0.0` until an independent review is resolved, the final tests pass from a clean checkout, API behavior and error handling are checked, and the operator workflow has been exercised end-to-end.
