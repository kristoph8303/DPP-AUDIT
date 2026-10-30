import unittest
from datetime import date, datetime, timezone
from pydantic import ValidationError

from dpp_audit.engine import (
    AccessStatus, Assessment, AssessmentOrigin, AssessmentState, Condition,
    ConditionOutcome, EvidenceRecord, EvidenceRequirement, Operator, OverallStatus,
    Policy, PolicyStatus, PublicationEligibility, Requirement, Rule, RuleReference,
    RuleStatus, Support, ValidationEngine, evaluate_condition, publication_eligibility,
)

D = date(2026, 10, 20)


def setup_case(status=PolicyStatus.ACTIVE, condition_value=True, min_evidence=0):
    policy = Policy(policy_id="P1", version="1", status=status, effective_date=date(2026, 1, 1),
        requirements=(Requirement(requirement_id="REQ1", text="Claim meets condition"),),
        rule_manifest=(RuleReference(rule_id="R1", rule_version="1"),))
    rule = Rule(rule_id="R1", rule_version="1", policy_id="P1", policy_version="1",
        requirement_id="REQ1", condition=Condition(field="claim.ok", operator=Operator.EQ, value=condition_value),
        claim_id_field="claim.id" if min_evidence else None, expected_result=True, evidence_requirement=EvidenceRequirement(minimum_count=min_evidence, minimum_quality=70))
    return policy, rule


def evidence():
    return EvidenceRecord(evidence_id="E1", claim_id="C1", source_name="Official source", source_type="official",
        source_reference="https://example.invalid/source", retrieved_date=date(2026, 10, 19),
        passage_or_location="section 2", access_status=AccessStatus.ACCESSIBLE, quality_score=90)


def assessment(state=AssessmentState.ACCEPTED, origin=AssessmentOrigin.HUMAN, support=Support.DIRECT):
    return Assessment(assessment_id="A1", evidence_id="E1", claim_id="C1", support=support,
        origin=origin, state=state, assessor_id="reviewer-1", assessed_at=datetime(2026, 10, 19, tzinfo=timezone.utc),
        rationale="Assessment recorded for test")


class CandidateEngineTests(unittest.TestCase):
    def test_passes_when_condition_passes_and_no_evidence_required(self):
        p, r = setup_case()
        result = ValidationEngine().run(p, [r], {"claim": {"ok": True}}, [], [], D)
        self.assertEqual(result.overall_status, OverallStatus.APPROVED)

    def test_mandatory_failure_rejects(self):
        p, r = setup_case()
        result = ValidationEngine().run(p, [r], {"claim": {"ok": False}}, [], [], D)
        self.assertEqual(result.overall_status, OverallStatus.REJECTED)

    def test_missing_field_is_indeterminate(self):
        p, r = setup_case()
        result = ValidationEngine().run(p, [r], {}, [], [], D)
        self.assertEqual(result.overall_status, OverallStatus.INDETERMINATE)

    def test_future_policy_is_not_publication_eligible_before_date(self):
        p, _ = setup_case()
        future = p.model_copy(update={"effective_date": date(2027, 1, 1)})
        self.assertEqual(publication_eligibility(future, D), PublicationEligibility.NOT_YET_EFFECTIVE)

    def test_retired_policy_can_be_historically_evaluated_but_not_used_for_new_publication(self):
        p, r = setup_case(PolicyStatus.RETIRED)
        result = ValidationEngine().run(p, [r], {"claim": {"ok": True}}, [], [], D)
        self.assertEqual(result.overall_status, OverallStatus.APPROVED)
        self.assertEqual(publication_eligibility(p, D), PublicationEligibility.RETIRED_POLICY)

    def test_manifest_mismatch_is_rejected(self):
        p, r = setup_case()
        bad = r.model_copy(update={"rule_version": "2"})
        with self.assertRaisesRegex(ValueError, "rule manifest"):
            ValidationEngine().run(p, [bad], {"claim": {"ok": True}}, [], [], D)

    def test_duplicate_evidence_ids_rejected(self):
        p, r = setup_case( min_evidence=1)
        ev = evidence()
        with self.assertRaisesRegex(ValueError, "duplicate evidence IDs"):
            ValidationEngine({"reviewer-1"}).run(p, [r], {"claim": {"ok": True, "id": "C1"}}, [ev, ev], [assessment()], D)

    def test_ai_assessment_cannot_be_accepted(self):
        with self.assertRaises(ValidationError):
            assessment(origin=AssessmentOrigin.AI, state=AssessmentState.ACCEPTED)

    def test_untrusted_assessor_does_not_satisfy_evidence_requirement(self):
        p, r = setup_case(min_evidence=1)
        result = ValidationEngine(set()).run(p, [r], {"claim": {"ok": True, "id": "C1"}}, [evidence()], [assessment()], D)
        self.assertEqual(result.overall_status, OverallStatus.INDETERMINATE)

    def test_authorized_accepted_assessment_can_satisfy_evidence_requirement(self):
        p, r = setup_case(min_evidence=1)
        result = ValidationEngine({"reviewer-1"}).run(p, [r], {"claim": {"ok": True, "id": "C1"}}, [evidence()], [assessment()], D)
        self.assertEqual(result.overall_status, OverallStatus.APPROVED)

    def test_contradiction_requires_review(self):
        p, r = setup_case(min_evidence=1)
        result = ValidationEngine({"reviewer-1"}).run(p, [r], {"claim": {"ok": True, "id": "C1"}}, [evidence()], [assessment(support=Support.CONTRADICTED)], D)
        self.assertEqual(result.overall_status, OverallStatus.REVIEW_REQUIRED)

    def test_inaccessible_evidence_requires_review(self):
        p, r = setup_case(min_evidence=1)
        ev = evidence().model_copy(update={"access_status": AccessStatus.INACCESSIBLE})
        result = ValidationEngine({"reviewer-1"}).run(p, [r], {"claim": {"ok": True, "id": "C1"}}, [ev], [assessment()], D)
        self.assertEqual(result.overall_status, OverallStatus.REVIEW_REQUIRED)

    def test_evidence_rule_without_claim_id_field_is_indeterminate(self):
        p, r = setup_case(min_evidence=1)
        r = r.model_copy(update={"claim_id_field": None})
        result = ValidationEngine({"reviewer-1"}).run(p, [r], {"claim": {"ok": True}}, [evidence()], [assessment()], D)
        self.assertEqual(result.overall_status, OverallStatus.INDETERMINATE)

    def test_nested_policy_lists_are_tuples(self):
        p, _ = setup_case()
        self.assertIsInstance(p.requirements, tuple)
        self.assertIsInstance(p.rule_manifest, tuple)

    def test_condition_bad_type_is_invalid_not_crash(self):
        c = Condition(field="x", operator=Operator.GT, value=10)
        outcome, _ = evaluate_condition(c, {"x": "not-a-number"})
        self.assertEqual(outcome, ConditionOutcome.INVALID)

    def test_fingerprint_changes_when_evaluation_date_changes(self):
        p, r = setup_case()
        engine = ValidationEngine()
        one = engine.run(p, [r], {"claim": {"ok": True}}, [], [], date(2026, 10, 20))
        two = engine.run(p, [r], {"claim": {"ok": True}}, [], [], date(2026, 10, 21))
        self.assertNotEqual(one.input_fingerprint, two.input_fingerprint)


if __name__ == "__main__":
    unittest.main(verbosity=2)
