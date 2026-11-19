# Hardening finding-to-test map

The verifier discovers tests by their `test_Cn_` or `test_Rn_` method names and reports one row per finding. The following tests provide representative coverage for each mapping; each module includes additional cases for its finding.

| Finding | Representative regression test |
|---|---|
| C1 | `tests/test_hardening_adapter.py::TestC1Header.test_C1_authorization_header_carries_the_real_key_as_bearer` |
| C2 | `tests/test_hardening_engine.py::TestC2PolicyStatus.test_C2_draft_policy_cannot_be_approved` |
| C3 | `tests/test_hardening_engine.py::TestC3Conflicts.test_C3_contradiction_not_hidden_by_order` |
| C4 | `tests/test_hardening_engine.py::TestC4ManualReview.test_C4_authorized_decision_clears_manual_rule` |
| C5 | `tests/test_hardening_engine.py::TestC5Fingerprint.test_C5_fingerprint_is_recomputable_from_archived_inputs` |
| C6 | `tests/test_hardening_engine.py::TestC6AuditTrail.test_C6_ignored_assessments_are_logged_with_reasons` |
| C7 | `tests/test_hardening_engine.py::TestC7Freshness.test_C7_old_publication_retrieved_recently_fails_age_limit` |
| C8 | `tests/test_hardening_engine.py::TestC8Injection.test_C8_csv_and_report_neutralize_hostile_free_text` |
| C9 | `tests/test_hardening_adapter.py::TestC9Snippet.test_C9_ai_summary_is_not_attached_to_urls` |
| C10 | `tests/test_hardening_adapter.py::TestC10Failures.test_C10_timeout_during_read_is_wrapped` |
| C11 | `tests/test_hardening_engine.py::TestC11ExpectedResult.test_C11_expected_false_inverts_condition` |
| C12 | `tests/test_hardening_engine.py::TestC12Comparisons.test_C12_bool_is_not_one` |
| C13 | `tests/test_hardening_engine.py::TestC13Failures.test_C13_run_safe_returns_indeterminate_record_on_bad_input` |
| C14 | `tests/test_hardening_adapter.py::TestC14Urls.test_C14_unsafe_urls_rejected` |
| R1 | `tests/test_hardening_engine.py::TestR1Signatures.test_R1_forged_unsigned_assessment_ignored_when_signatures_required` |
| R2 | `tests/test_hardening_engine.py::TestR2ClaimBinding.test_R2_matching_text_hash_passes` |
| R3 | `tests/test_hardening_engine.py::TestR3R4R5.test_R3_same_source_counted_once` |
| R4 | `tests/test_hardening_engine.py::TestR3R4R5.test_R4_changed_evidence_after_assessment_is_ignored` |
| R5 | `tests/test_hardening_engine.py::TestR3R4R5.test_R5_evidence_scoped_to_other_requirement_is_not_used` |
| R6 | `tests/test_hardening_engine.py::TestR6R7Reporting.test_R6_failing_optional_rule_is_surfaced_as_warning` |
| R7 | `tests/test_hardening_engine.py::TestR6R7Reporting.test_R7_every_export_carries_the_caveat` |
| R8 | `tests/test_hardening_adapter.py::TestR8R9.test_R8_query_is_capped_and_control_characters_removed` |
| R9 | `tests/test_hardening_adapter.py::TestR8R9.test_R9_structured_search_results_supply_titles` |

Run `python scripts/verify_hardening.py` from the package root. The script verifies that every identifier has at least one executed test and checks the demo outputs. A mapping is evidence of coverage organization; it is not proof that every possible failure mode is eliminated.
