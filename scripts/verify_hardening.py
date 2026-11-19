#!/usr/bin/env python3
"""Run the full DPP-AUDIT test suite plus the demo and print a per-finding PASS/FAIL table.

Usage (from the repository root):  python scripts/verify_hardening.py
Exit code 0 only if every test passes, the demo runs, and every finding has at least one test.
Requires: pip install -r requirements.txt (pydantic 2.x). No network access is used.
"""
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

FINDINGS = OrderedDict([
    ("C1", "Authorization header sent as literal asterisks"),
    ("C2", "Draft/retired/future policy status ignored by run()"),
    ("C3", "Contradicting assessments hidden by list order"),
    ("C4", "Manual-review rules could never be cleared"),
    ("C5", "Fingerprint omitted assessor allowlist / not recomputable"),
    ("C6", "Ignored assessments left no audit trail"),
    ("C7", "Freshness used retrieval date, not publication date"),
    ("C8", "Report/CSV injection via free-text IDs"),
    ("C9", "AI summary attached to every URL as a snippet"),
    ("C10", "Network failures escaped; no retry/size cap"),
    ("C11", "Rule.expected_result was unused"),
    ("C12", "Loose comparison semantics"),
    ("C13", "Failures produced no run record"),
    ("C14", "Unsafe / duplicate candidate URLs accepted"),
    ("R1", "Assessor identity self-declared (signatures, separation of duties)"),
    ("R2", "Evidence not bound to claim wording"),
    ("R3", "Duplicate sources counted separately"),
    ("R4", "Self-asserted quality/type could change after assessment"),
    ("R5", "Evidence not scoped per requirement"),
    ("R6", "Failing optional rules invisible"),
    ("R7", "APPROVED shown without caveat in exports"),
    ("R8", "Query size/control characters/prompt-injection hygiene"),
    ("R9", "Structured provider results not parsed"),
])


class Recorder(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.outcomes = []          # (test name, ok)

    def addSuccess(self, test):
        super().addSuccess(test); self.outcomes.append((test.id(), True))

    def addFailure(self, test, err):
        super().addFailure(test, err); self.outcomes.append((test.id(), False))

    def addError(self, test, err):
        super().addError(test, err); self.outcomes.append((test.id(), False))


def main() -> int:
    try:
        import pydantic  # noqa: F401
    except ImportError:
        print("pydantic is not installed. Run: python -m pip install -r requirements.txt")
        return 2
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests"))
    runner = unittest.TextTestRunner(resultclass=Recorder, verbosity=0, stream=io.StringIO())
    result = runner.run(suite)

    per = {k: [] for k in FINDINGS}
    for name, ok in result.outcomes:
        m = re.search(r"\.test_(C\d+|R\d+)_", name)
        if m:
            per[m.group(1)].append(ok)

    print(f"{'ID':<4} {'RESULT':<8} {'TESTS':<6} FINDING")
    all_ok = True
    for key, title in FINDINGS.items():
        oks = per[key]
        status = "NO TEST" if not oks else ("PASS" if all(oks) else "FAIL")
        all_ok &= status == "PASS"
        print(f"{key:<4} {status:<8} {len(oks):<6} {title}")
    print(f"\nTotal tests: {result.testsRun}  failures: {len(result.failures)}  errors: {len(result.errors)}")
    for test, tb in result.failures + result.errors:
        print("\n--- FAILED:", test.id(), "\n", tb)

    with tempfile.TemporaryDirectory() as tmp:
        demo = subprocess.run([sys.executable, str(ROOT / "demo.py")], cwd=tmp, capture_output=True, text=True,
                              env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(ROOT), os.environ.get("PYTHONPATH", "")]))})
        produced = sorted(p.name for p in (Path(tmp) / "output").glob("*")) if (Path(tmp) / "output").exists() else []
    demo_ok = demo.returncode == 0 and produced == ["audit.csv", "human_report.txt", "validation_run.json"]
    print(f"Demo: {'PASS' if demo_ok else 'FAIL'}  ({demo.stdout.strip().splitlines()[0] if demo.stdout.strip() else demo.stderr.strip()[-200:]})")
    print("\nNote: passing tests do not authenticate sources or establish production readiness.")
    return 0 if (result.wasSuccessful() and all_ok and demo_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
