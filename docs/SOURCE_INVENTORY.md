# Source inventory

## Examined artifacts

1. **Public DPP-AUDIT source:** repository `kristoph8303/DPP-AUDIT`, commit `333c513c26cc1411840352388c36e835f308f6b0`.
   - `dpp_audit/engine.py`, Git blob `a9ff0eea47c1cad4560e5f9f0e6eed0fbeb0e34d`.
   - `tests/test_engine.py`, Git blob `739fad19f13a8d220cc9f65a5590e1476e658f3c` (16 named engine tests).
   - [`README.md`](https://github.com/kristoph8303/DPP-AUDIT/blob/333c513c26cc1411840352388c36e835f308f6b0/README.md) identifies this repository as an audit candidate and documents its limits.

2. **Hardened repository source:** copied from the existing local 1.1.0-candidate output. This package contains `dpp_audit/engine.py`, `dpp_audit/perplexity_adapter.py`, `demo.py`, four test modules, and `scripts/verify_hardening.py`.
   - Engine SHA-256: `7174574b2f9ba3a55a09301da56c66ca384a11ab9c77a7f86a08ad3c5c53d60e`.
   - The source defines `ENGINE_VERSION = "1.1.0-candidate"`.
   - The supplied test file names include regression tests for each C1–C14 and R1–R9 finding; see [the hardening matrix](HARDENING_MATRIX.md).

3. **User-supplied hardening script:** the exact 23 finding descriptions were read from the `verify_hardening.py` attachment in “Production Readiness Audit.” The copy included here has the same text and logic; line-ending differences account for its byte hash differing from the attachment. It checks test-name coverage, executes the suite, and checks that the demo creates exactly `audit.csv`, `human_report.txt`, and `validation_run.json`.
   - Attachment SHA-256: `55c7f89a0380b2bb8d7f0ec17dee522d248b585376618c978984345523569987`.
   - Included script SHA-256: `a3026ffa4334c266638533b3c7a7571a1bf70e014417d2e552ba0908537b5413`.

4. **Supplemental uploaded engine:** an earlier attached `engine.py` identifies itself as `1.0.0-candidate`. Its line-ending-normalized SHA-256 is `523935f6822c05b7f68e14a0e29010dd04affcacf4c2a2a607b2c6aa3916ef00`. It was inspected as a separate artifact. It is not the missing 1.2.0 source and is not silently substituted for it.

## Missing source

The 1.2.0-pre-freeze engine and matching tests are not present in the referenced conversation's attachments or in the inspected local candidate folders. The referenced conversation itself contains only two user messages and no source attachment; the associated prior “Production Readiness Audit” conversation has the hardening script attachment but no 1.2.0 source attachment. This is why the comparison and merge remain provisional.

## Reproduction

The source paths above are provenance notes, not runtime dependencies. This package runs from its own folder and does not modify the original repo, the earlier candidate folder, or GitHub.
