"""Regression tests for every finding in the break-it review (C = confirmed defect, R = design risk).
Test names start with the finding ID so verify_hardening.py can report per-finding results."""
import csv, io, os, tempfile, unittest
from datetime import date, datetime, timezone

from dpp_audit.engine import (
    AccessStatus, Assessment, AssessmentOrigin, AssessmentState, Condition, ConditionOutcome,
    EvidenceRecord, EvidenceRequirement, Operator, OverallStatus, Policy, PolicyStatus,
    PublicationEligibility, Requirement, ReviewDecision, ReviewDecisionOutcome, Rule, RuleReference,
    RuleStatus, Support, ValidationEngine, canonical_fingerprint, claim_text_fingerprint,
    compute_input_fingerprint, evaluate_condition, evidence_fingerprint, export_audit_csv,
    export_human_report, export_json, human_report, sign_assessment, sign_review_decision,
)

D = date(2026, 10, 20)
INPUT = {"claim": {"ok": True, "id": "C1", "text": "The sky is blue"}}


def make_policy(status=PolicyStatus.ACTIVE, effective=date(2026, 1, 1), extra_rules=(), manual=False):
    reqs = [Requirement(requirement_id="REQ1", text="Claim meets condition", manual_review_only=manual)]
    manifest = [RuleReference(rule_id="R1", rule_version="1")]
    for rid, mandatory in extra_rules:
        reqs.append(Requirement(requirement_id="REQ-" + rid, text="extra", mandatory=mandatory))
        manifest.append(RuleReference(rule_id=rid, rule_version="1"))
    return Policy(policy_id="P1", version="1", status=status, effective_date=effective,
                  requirements=tuple(reqs), rule_manifest=tuple(manifest))


def make_rule(rid="R1", req="REQ1", cond=None, min_ev=0, mandatory=True, manual=False, expected=True,
              claim_text_field=None, **evreq):
    cond = cond if cond is not None else Condition(field="claim.ok", operator=Operator.EQ, value=True)
    return Rule(rule_id=rid, rule_version="1", policy_id="P1", policy_version="1", requirement_id=req,
                condition=cond, claim_id_field="claim.id" if min_ev else None, expected_result=expected,
                mandatory=mandatory, manual_review_required=manual, claim_text_field=claim_text_field,
                evidence_requirement=EvidenceRequirement(minimum_count=min_ev, minimum_quality=70, **evreq))


def make_evidence(eid="E1", ref="https://example.invalid/source", **kw):
    base = dict(evidence_id=eid, claim_id="C1", source_name="Official source", source_type="official",
                source_reference=ref, retrieved_date=date(2026, 10, 19), passage_or_location="section 2",
                access_status=AccessStatus.ACCESSIBLE, quality_score=90)
    base.update(kw)
    return EvidenceRecord(**base)


def make_assessment(aid="A1", eid="E1", support=Support.DIRECT, who="reviewer-1", at=datetime(2026, 10, 19, tzinfo=timezone.utc), **kw):
    base = dict(assessment_id=aid, evidence_id=eid, claim_id="C1", support=support, origin=AssessmentOrigin.HUMAN,
                state=AssessmentState.ACCEPTED, assessor_id=who, assessed_at=at, rationale="Test assessment")
    base.update(kw)
    return Assessment(**base)


def run(rules, evidence=(), assessments=(), policy=None, engine=None, data=None, decisions=(), when=D):
    return (engine or ValidationEngine({"reviewer-1"})).run(
        policy or make_policy(), rules, data or INPUT, evidence, assessments, when, decisions)


class TestC2PolicyStatus(unittest.TestCase):
    def test_C2_run_records_eligibility_for_retired_and_future_policies(self):
        retired = run([make_rule()], policy=make_policy(PolicyStatus.RETIRED))
        self.assertEqual(retired.overall_status, OverallStatus.APPROVED)       # historical rule kept
        self.assertEqual(retired.publication_eligibility, PublicationEligibility.RETIRED_POLICY)
        future = run([make_rule()], policy=make_policy(effective=date(2027, 1, 1)))
        self.assertEqual(future.publication_eligibility, PublicationEligibility.NOT_YET_EFFECTIVE)
        self.assertIn("publication_eligibility=not_yet_effective", future.audit_trail)

    def test_C2_draft_policy_cannot_be_approved(self):
        r = run([make_rule()], policy=make_policy(PolicyStatus.DRAFT))
        self.assertEqual(r.overall_status, OverallStatus.REVIEW_REQUIRED)
        self.assertEqual(r.publication_eligibility, PublicationEligibility.DRAFT_POLICY)

    def test_C2_active_policy_still_approved(self):
        r = run([make_rule()])
        self.assertEqual(r.overall_status, OverallStatus.APPROVED)
        self.assertEqual(r.publication_eligibility, PublicationEligibility.ELIGIBLE_FOR_CONSIDERATION)


class TestC3Conflicts(unittest.TestCase):
    def _both(self, order):
        a1, a2 = make_assessment("A1", support=Support.DIRECT), make_assessment("A2", support=Support.CONTRADICTED)
        return run([make_rule(min_ev=1)], [make_evidence()], [a1, a2] if order else [a2, a1])

    def test_C3_contradiction_not_hidden_by_order(self):
        self.assertEqual(self._both(True).overall_status, OverallStatus.REVIEW_REQUIRED)
        self.assertEqual(self._both(False).overall_status, OverallStatus.REVIEW_REQUIRED)

    def test_C3_conflicting_supports_need_review(self):
        a1, a2 = make_assessment("A1", support=Support.DIRECT), make_assessment("A2", support=Support.PARTIAL)
        r = run([make_rule(min_ev=1)], [make_evidence()], [a1, a2])
        self.assertEqual(r.overall_status, OverallStatus.REVIEW_REQUIRED)
        self.assertTrue(any("conflicting" in m for m in r.rule_results[0].missing_information))

    def test_C3_agreeing_assessments_still_approve(self):
        r = run([make_rule(min_ev=1)], [make_evidence()], [make_assessment("A1"), make_assessment("A2")])
        self.assertEqual(r.overall_status, OverallStatus.APPROVED)


class TestC4ManualReview(unittest.TestCase):
    RULE = lambda self: make_rule(manual=True)
    POL = lambda self: make_policy(manual=True)

    def decision(self, did="D1", outcome=ReviewDecisionOutcome.APPROVED, who="reviewer-1"):
        return ReviewDecision(decision_id=did, rule_id="R1", rule_version="1", decision=outcome,
                              reviewer_id=who, decided_at=datetime(2026, 10, 19, tzinfo=timezone.utc), rationale="Reviewed")

    def test_C4_manual_rule_without_decision_still_requires_review(self):
        self.assertEqual(run([self.RULE()], policy=self.POL()).overall_status, OverallStatus.REVIEW_REQUIRED)

    def test_C4_authorized_decision_clears_manual_rule(self):
        r = run([self.RULE()], policy=self.POL(), decisions=[self.decision()])
        self.assertEqual(r.overall_status, OverallStatus.APPROVED)
        self.assertEqual(r.rule_results[0].decision_ids, ("D1",))

    def test_C4_rejection_rejects(self):
        r = run([self.RULE()], policy=self.POL(), decisions=[self.decision(outcome=ReviewDecisionOutcome.REJECTED)])
        self.assertEqual(r.overall_status, OverallStatus.REJECTED)

    def test_C4_unauthorized_or_conflicting_decisions_do_not_clear(self):
        r = run([self.RULE()], policy=self.POL(), decisions=[self.decision(who="stranger")])
        self.assertEqual(r.overall_status, OverallStatus.REVIEW_REQUIRED)
        self.assertTrue(any("review decision D1 ignored" in t for t in r.audit_trail))
        both = [self.decision("D1"), self.decision("D2", ReviewDecisionOutcome.REJECTED)]
        self.assertEqual(run([self.RULE()], policy=self.POL(), decisions=both).overall_status, OverallStatus.REVIEW_REQUIRED)

    def test_C4_decision_for_unknown_rule_rejected(self):
        bad = self.decision().model_copy(update={"rule_id": "NOPE"})
        with self.assertRaisesRegex(ValueError, "unknown rule"):
            run([self.RULE()], policy=self.POL(), decisions=[bad])


class TestC5Fingerprint(unittest.TestCase):
    def test_C5_allowlist_changes_fingerprint_and_is_reported(self):
        a = run([make_rule(min_ev=1)], [make_evidence()], [make_assessment()], engine=ValidationEngine({"reviewer-1"}))
        b = run([make_rule(min_ev=1)], [make_evidence()], [make_assessment()], engine=ValidationEngine(set()))
        self.assertNotEqual(a.input_fingerprint, b.input_fingerprint)
        self.assertNotEqual(a.assessor_allowlist_sha256, b.assessor_allowlist_sha256)
        self.assertIn("assessor_allowlist_sha256", export_json_text(a))

    def test_C5_fingerprint_is_recomputable_from_archived_inputs(self):
        rules, ev, asm = [make_rule(min_ev=1)], [make_evidence()], [make_assessment()]
        r = run(rules, ev, asm)
        again = compute_input_fingerprint(policy=make_policy(), rules=rules, input_data=INPUT, evidence=ev,
                                          assessments=asm, evaluation_date=D, authorized_assessor_ids={"reviewer-1"})
        self.assertEqual(r.input_fingerprint, again)

    def test_C5_fingerprint_distinguishes_types(self):
        self.assertNotEqual(canonical_fingerprint({"a": date(2026, 1, 1)}), canonical_fingerprint({"a": "2026-01-01"}))
        self.assertNotEqual(canonical_fingerprint({"a": b"ab"}), canonical_fingerprint({"a": "6162"}))
        with self.assertRaises(ValueError):
            canonical_fingerprint({1: "a", "1": "b"})


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def export_json_text(run_):
    with tempfile.TemporaryDirectory() as d:
        p = export_json(run_, os.path.join(d, "r.json"))
        return read(p)


class TestC6AuditTrail(unittest.TestCase):
    def test_C6_ignored_assessments_are_logged_with_reasons(self):
        r = run([make_rule(min_ev=1)], [make_evidence()], [make_assessment("A1", who="stranger"),
                make_assessment("A2", support=Support.DIRECT, state=AssessmentState.PROPOSED, origin=AssessmentOrigin.AI)])
        trail = "\n".join(r.audit_trail)
        self.assertIn("assessment A1 ignored: assessor not authorized", trail)
        self.assertIn("assessment A2 ignored: not accepted", trail)
        self.assertIn("Records ignored", human_report(r))

    def test_C6_future_dated_assessment_ignored(self):
        r = run([make_rule(min_ev=1)], [make_evidence()], [make_assessment(at=datetime(2026, 12, 1, tzinfo=timezone.utc))])
        self.assertEqual(r.overall_status, OverallStatus.INDETERMINATE)
        self.assertIn("assessment A1 ignored: assessed after the evaluation date", r.audit_trail)

    def test_C6_naive_datetime_assessment_rejected(self):
        with self.assertRaises(ValueError):
            make_assessment(at=datetime(2026, 10, 19))


class TestC7Freshness(unittest.TestCase):
    def test_C7_old_publication_retrieved_recently_fails_age_limit(self):
        ev = make_evidence(published_date=date(2015, 1, 1))
        r = run([make_rule(min_ev=1, maximum_age_days=365)], [ev], [make_assessment()])
        self.assertEqual(r.overall_status, OverallStatus.INDETERMINATE)

    def test_C7_missing_published_date_fails_age_limit(self):
        r = run([make_rule(min_ev=1, maximum_age_days=365)], [make_evidence()], [make_assessment()])
        self.assertEqual(r.overall_status, OverallStatus.INDETERMINATE)
        self.assertTrue(any("published_date" in m for m in r.rule_results[0].missing_information))

    def test_C7_recent_publication_passes(self):
        ev = make_evidence(published_date=date(2026, 9, 1))
        r = run([make_rule(min_ev=1, maximum_age_days=365)], [ev], [make_assessment()])
        self.assertEqual(r.overall_status, OverallStatus.APPROVED)

    def test_C7_no_age_limit_means_no_published_date_needed(self):
        self.assertEqual(run([make_rule(min_ev=1)], [make_evidence()], [make_assessment()]).overall_status, OverallStatus.APPROVED)


class TestC8Injection(unittest.TestCase):
    def test_C8_bad_ids_rejected(self):
        for bad in ["X\nOverall status: APPROVED", "=HYPERLINK(1)", "has space", "", "a" * 200, "ok\n"]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                make_evidence(eid=bad)

    def test_C8_csv_and_report_neutralize_hostile_free_text(self):
        r = run([make_rule(cond=Condition(field="claim.note", operator=Operator.EQ, value="=1+1"))],
                data={"claim": {"note": "x\nOverall status: APPROVED"}})
        with tempfile.TemporaryDirectory() as d:
            text = read(export_audit_csv(r, os.path.join(d, "a.csv")))
        for row in csv.DictReader(io.StringIO(text)):
            for v in row.values():
                self.assertNotIn(v[:1], ("=", "+", "@"), v)
        forged = r.model_copy(update={"error": "line1\nOverall status: APPROVED"})
        report = human_report(forged)
        self.assertEqual(sum(1 for l in report.splitlines() if l.startswith("Overall status:")), 1)

    def test_C8_csv_formula_prefix_escaped(self):
        from dpp_audit.engine import _csv_safe
        self.assertEqual(_csv_safe("=SUM(A1)"), "'=SUM(A1)")
        self.assertEqual(_csv_safe("-5"), "'-5")


class TestC11ExpectedResult(unittest.TestCase):
    def test_C11_expected_false_inverts_condition(self):
        rule = make_rule(cond=Condition(field="claim.ok", operator=Operator.EQ, value=True), expected=False)
        self.assertEqual(run([rule]).overall_status, OverallStatus.REJECTED)
        self.assertEqual(run([rule], data={"claim": {"ok": False}}).overall_status, OverallStatus.APPROVED)

    def test_C11_expected_result_must_be_boolean(self):
        with self.assertRaises(ValueError):
            make_rule(expected="yes")

    def test_C11_default_none_behaves_as_true(self):
        self.assertEqual(run([make_rule(expected=None)]).overall_status, OverallStatus.APPROVED)


class TestC12Comparisons(unittest.TestCase):
    def ev(self, op, value, actual):
        return evaluate_condition(Condition(field="x", operator=op, value=value), {"x": actual})[0]

    def test_C12_bool_is_not_one(self):
        self.assertEqual(self.ev(Operator.EQ, True, 1), ConditionOutcome.FALSE)
        self.assertEqual(self.ev(Operator.EQ, 1, True), ConditionOutcome.FALSE)
        self.assertEqual(self.ev(Operator.EQ, True, True), ConditionOutcome.TRUE)
        self.assertEqual(self.ev(Operator.NEQ, True, 1), ConditionOutcome.TRUE)

    def test_C12_numbers_still_compare(self):
        self.assertEqual(self.ev(Operator.EQ, 1, 1.0), ConditionOutcome.TRUE)
        self.assertEqual(self.ev(Operator.GT, 5, 10), ConditionOutcome.TRUE)
        self.assertEqual(self.ev(Operator.GT, 5, True), ConditionOutcome.INVALID)

    def test_C12_in_rejects_string_substring_semantics(self):
        self.assertEqual(self.ev(Operator.IN, "abc", "a"), ConditionOutcome.INVALID)
        self.assertEqual(self.ev(Operator.IN, ["a", "b"], "a"), ConditionOutcome.TRUE)
        self.assertEqual(self.ev(Operator.IN, [1], True), ConditionOutcome.FALSE)

    def test_C12_exists_needs_a_real_boolean(self):
        self.assertEqual(self.ev(Operator.EXISTS, "false", 1), ConditionOutcome.INVALID)
        self.assertEqual(self.ev(Operator.EXISTS, False, 1), ConditionOutcome.FALSE)
        self.assertEqual(self.ev(Operator.EXISTS, None, 1), ConditionOutcome.TRUE)

    def test_C12_dotted_literal_keys_resolve(self):
        out, _ = evaluate_condition(Condition(field="a.b", operator=Operator.EQ, value=1), {"a.b": 1})
        self.assertEqual(out, ConditionOutcome.TRUE)
        out, _ = evaluate_condition(Condition(field="a.b", operator=Operator.EQ, value=2), {"a": {"b": 2}})
        self.assertEqual(out, ConditionOutcome.TRUE)

    def test_C12_reason_truncates_long_values(self):
        _, reason = evaluate_condition(Condition(field="x", operator=Operator.EQ, value="y"), {"x": "s" * 500})
        self.assertLess(len(reason), 200)


class TestC13Failures(unittest.TestCase):
    def test_C13_run_safe_returns_indeterminate_record_on_bad_input(self):
        eng = ValidationEngine({"reviewer-1"})
        for bad in [{"claim": {"ok": True, "x": float("nan")}}, {"claim": {"ok": True, "x": object()}}]:
            r = eng.run_safe(make_policy(), [make_rule()], bad, [], [], D)
            self.assertEqual(r.overall_status, OverallStatus.INDETERMINATE)
            self.assertIsNotNone(r.error)
        r = eng.run_safe(make_policy(), [make_rule()], INPUT, [make_evidence(), make_evidence()], [], D)
        self.assertIn("duplicate evidence IDs", r.error)

    def test_C13_sets_and_bytes_in_input_are_supported(self):
        r = run([make_rule()], data={"claim": {"ok": True, "tags": {"b", "a"}, "raw": b"\x00"}})
        self.assertEqual(r.overall_status, OverallStatus.APPROVED)

    def test_C13_run_still_raises_for_manifest_mismatch(self):
        with self.assertRaisesRegex(ValueError, "rule manifest"):
            run([make_rule().model_copy(update={"rule_version": "2"})])


class TestR1Signatures(unittest.TestCase):
    KEY = b"k" * 32

    def eng(self, **kw):
        return ValidationEngine({"reviewer-1"}, assessor_keys={"reviewer-1": self.KEY}, require_signatures=True, **kw)

    def signed(self, ev=None, **kw):
        ev = ev or make_evidence()
        return sign_assessment(make_assessment(evidence_sha256=evidence_fingerprint(ev), **kw), self.KEY)

    def test_R1_forged_unsigned_assessment_ignored_when_signatures_required(self):
        r = run([make_rule(min_ev=1)], [make_evidence()], [make_assessment()], engine=self.eng())
        self.assertEqual(r.overall_status, OverallStatus.INDETERMINATE)

    def test_R1_valid_signature_accepted(self):
        ev = make_evidence()
        r = run([make_rule(min_ev=1)], [ev], [self.signed(ev)], engine=self.eng())
        self.assertEqual(r.overall_status, OverallStatus.APPROVED)

    def test_R1_tampered_signed_assessment_rejected(self):
        ev = make_evidence()
        tampered = self.signed(ev).model_copy(update={"support": Support.DIRECT, "rationale": "changed after signing"})
        r = run([make_rule(min_ev=1)], [ev], [tampered], engine=self.eng())
        self.assertEqual(r.overall_status, OverallStatus.INDETERMINATE)
        self.assertIn("assessment A1 ignored: signature invalid", r.audit_trail)

    def test_R1_wrong_key_rejected_and_bad_signature_rejected_even_when_optional(self):
        ev = make_evidence()
        forged = sign_assessment(make_assessment(evidence_sha256=evidence_fingerprint(ev)), b"x" * 32)
        eng = ValidationEngine({"reviewer-1"}, assessor_keys={"reviewer-1": self.KEY})
        self.assertEqual(run([make_rule(min_ev=1)], [ev], [forged], engine=eng).overall_status, OverallStatus.INDETERMINATE)

    def test_R1_signed_review_decision(self):
        pol, rule = make_policy(manual=True), make_rule(manual=True)
        d = ReviewDecision(decision_id="D1", rule_id="R1", rule_version="1", decision=ReviewDecisionOutcome.APPROVED,
                           reviewer_id="reviewer-1", decided_at=datetime(2026, 10, 19, tzinfo=timezone.utc), rationale="ok")
        self.assertEqual(run([rule], policy=pol, decisions=[d], engine=self.eng()).overall_status, OverallStatus.REVIEW_REQUIRED)
        self.assertEqual(run([rule], policy=pol, decisions=[sign_review_decision(d, self.KEY)], engine=self.eng()).overall_status, OverallStatus.APPROVED)

    def test_R1_collector_cannot_assess_own_evidence(self):
        ev = make_evidence(collected_by="reviewer-1")
        r = run([make_rule(min_ev=1)], [ev], [make_assessment()])
        self.assertEqual(r.overall_status, OverallStatus.INDETERMINATE)
        self.assertIn("assessment A1 ignored: assessor also collected the evidence", r.audit_trail)


class TestR2ClaimBinding(unittest.TestCase):
    def rule(self):
        return make_rule(min_ev=1, claim_text_field="claim.text")

    def test_R2_matching_text_hash_passes(self):
        h = claim_text_fingerprint("The sky is blue")
        r = run([self.rule()], [make_evidence(claim_text_sha256=h)], [make_assessment(claim_text_sha256=h)])
        self.assertEqual(r.overall_status, OverallStatus.APPROVED)

    def test_R2_reworded_claim_needs_review(self):
        h = claim_text_fingerprint("The sky is green")
        r = run([self.rule()], [make_evidence(claim_text_sha256=h)], [make_assessment(claim_text_sha256=h)])
        self.assertEqual(r.overall_status, OverallStatus.REVIEW_REQUIRED)

    def test_R2_evidence_without_hash_does_not_count(self):
        r = run([self.rule()], [make_evidence()], [make_assessment()])
        self.assertEqual(r.overall_status, OverallStatus.INDETERMINATE)

    def test_R2_assessment_for_other_wording_ignored(self):
        h = claim_text_fingerprint("The sky is blue")
        r = run([self.rule()], [make_evidence(claim_text_sha256=h)],
                [make_assessment(claim_text_sha256=claim_text_fingerprint("other"))])
        self.assertEqual(r.overall_status, OverallStatus.INDETERMINATE)


class TestR3R4R5(unittest.TestCase):
    def test_R3_same_source_counted_once(self):
        evs = [make_evidence("E1", "https://example.invalid/Source/"), make_evidence("E2", "HTTPS://EXAMPLE.invalid/Source#frag")]
        asm = [make_assessment("A1", "E1"), make_assessment("A2", "E2")]
        r = run([make_rule(min_ev=2)], evs, asm)
        self.assertEqual(r.overall_status, OverallStatus.INDETERMINATE)
        self.assertIn("1/2 distinct sources", r.rule_results[0].missing_information[0])

    def test_R3_two_distinct_sources_pass(self):
        evs = [make_evidence("E1", "https://a.example/x"), make_evidence("E2", "https://b.example/y")]
        asm = [make_assessment("A1", "E1"), make_assessment("A2", "E2")]
        self.assertEqual(run([make_rule(min_ev=2)], evs, asm).overall_status, OverallStatus.APPROVED)

    def test_R4_changed_evidence_after_assessment_is_ignored(self):
        original = make_evidence()
        asm = make_assessment(evidence_sha256=evidence_fingerprint(original))
        inflated = original.model_copy(update={"quality_score": 100, "source_type": "official"})
        r = run([make_rule(min_ev=1)], [inflated], [asm])
        self.assertEqual(r.overall_status, OverallStatus.INDETERMINATE)
        self.assertIn("assessment A1 ignored: evidence changed since it was assessed", r.audit_trail)

    def test_R5_evidence_scoped_to_other_requirement_is_not_used(self):
        ev = make_evidence(requirement_ids=("REQ-OTHER",))
        self.assertEqual(run([make_rule(min_ev=1)], [ev], [make_assessment()]).overall_status, OverallStatus.INDETERMINATE)
        ev2 = make_evidence(requirement_ids=("REQ1",))
        self.assertEqual(run([make_rule(min_ev=1)], [ev2], [make_assessment()]).overall_status, OverallStatus.APPROVED)


class TestR6R7Reporting(unittest.TestCase):
    def test_R6_failing_optional_rule_is_surfaced_as_warning(self):
        pol = make_policy(extra_rules=[("R2", False)])
        opt = make_rule("R2", "REQ-R2", cond=Condition(field="claim.optional", operator=Operator.EQ, value=True), mandatory=False)
        r = run([make_rule(), opt], policy=pol, data={"claim": {"ok": True, "optional": False}})
        self.assertEqual(r.overall_status, OverallStatus.APPROVED)       # status rule unchanged
        self.assertEqual(r.warnings, ("non-mandatory rule R2 is fail",))
        self.assertIn("Warnings:", human_report(r))

    def test_R7_every_export_carries_the_caveat(self):
        r = run([make_rule()])
        self.assertIn("not a guarantee", r.caveat)
        with tempfile.TemporaryDirectory() as d:
            j = read(export_json(r, os.path.join(d, "r.json")))
            c = read(export_audit_csv(r, os.path.join(d, "r.csv")))
            h = read(export_human_report(r, os.path.join(d, "r.txt")))
        for text in (j, c, h):
            self.assertIn("not a guarantee", text)
        self.assertIn("Overall status: APPROVED (rules-based result; not a truth guarantee)", h)

    def test_exports_are_written_atomically_and_leave_no_temp_files(self):
        r = run([make_rule()])
        with tempfile.TemporaryDirectory() as d:
            export_json(r, os.path.join(d, "r.json"))
            export_json(r, os.path.join(d, "r.json"))
            self.assertEqual(os.listdir(d), ["r.json"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
