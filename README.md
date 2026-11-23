# DPP-AUDIT — deterministic-first freeze candidate

**Status: review candidate only. It is not frozen, production-ready, or independently certified.** This package uses the source-backed hardened 1.1.0 candidate as its base. The exact 1.2.0-pre-freeze source and tests were not recoverable from the referenced chat or available workspaces, so the three-way source comparison is incomplete; see [candidate comparison](docs/CANDIDATE_COMPARISON.md).

## What is included

- A deterministic policy/evidence engine with separate evidence and assessment records.
- Policy lifecycle and publication-eligibility reporting, manual-review decisions, conflict handling, source and requirement scoping, input fingerprints, and audit exports.
- An isolated Perplexity discovery adapter. Its results remain unverified candidates and do not authorize decisions.
- Regression tests mapped to all 23 supplied findings (C1–C14 and R1–R9).
- A synthetic demo that writes `output/audit.csv`, `output/human_report.txt`, and `output/validation_run.json`.

`APPROVED` means only that the configured rules passed on the supplied records. It is not a guarantee that a claim is true or that a source is authentic.

## Run it on Windows

Open PowerShell in this folder and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\verify_hardening.py
.\.venv\Scripts\python.exe demo.py
Get-ChildItem output\audit.csv, output\human_report.txt, output\validation_run.json
```

The first test command prints individual tests. The hardening verifier runs the suite again, prints a C1–C14/R1–R9 coverage table, and checks the demo in a temporary directory for exactly the three named files.

## Run it on macOS or Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/verify_hardening.py
python demo.py
ls output/audit.csv output/human_report.txt output/validation_run.json
```

The demo uses synthetic data and `example.invalid`; it makes no live source-verification claim. The regression suite does not make a live Perplexity request.

## Review notes and limits

- [Candidate comparison and selection](docs/CANDIDATE_COMPARISON.md)
- [Source inventory](docs/SOURCE_INVENTORY.md)
- [Hardening finding-to-test map](docs/HARDENING_MATRIX.md)
- [Unresolved limitations](docs/LIMITATIONS.md)
- [Test status for this assembled copy](TEST_RESULTS.txt)

The 1.2.0 source gap must be closed before claiming that this package incorporates a verified three-way comparison. Passing the included tests would still not establish production readiness or source authenticity.

## Customer intake UI preview

The UI prototype demonstrates the intended Backed Claims customer flow: add material, view a Quick Claims Sheet (an early map of possible claim passages), then see that the full audit is up for human review. The sheet does not promise the final audit's scope or a verified verdict. Claim colors identify subject type only; they do not grade the writing. Review language describes how sources relate to the wording, rather than judging the writer.

Open ui/index.html in a browser. The preview has no server or external font dependency.

This is a local, front-end prototype. It does not upload or store customer material, check sources, extract PDF text, create a human-review queue, or send a completed audit. The sample scanner uses simple text patterns and can miss or misclassify claims. Its “Up for human review” label demonstrates the proposed experience only; it is not a real submission receipt. The tone cards show the same Eiffel Tower fact in four styles with subtle CSS scene motion. A selected tone stays in the current page only and is not applied to the submitted material.

## Optional Perplexity use

Only when you choose to make a live request, set `PERPLEXITY_API_KEY` in your private environment. Never place the key in source code, fixtures, or Git. A live request sends the search query to the provider and may incur charges.
