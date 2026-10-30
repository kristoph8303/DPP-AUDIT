"""Runnable end-to-end engine demo using synthetic, explicitly illustrative records."""
from datetime import date, datetime, timezone
from dpp_audit.engine import (
    AccessStatus, Assessment, AssessmentOrigin, AssessmentState, Condition,
    EvidenceRecord, EvidenceRequirement, Operator, Policy, PolicyStatus,
    Requirement, Rule, RuleReference, Support, ValidationEngine,
    export_audit_csv, export_human_report, export_json,
)

policy = Policy(
    policy_id="CONTENT-AUDIT-DEMO", version="1.0", status=PolicyStatus.ACTIVE,
    effective_date=date(2026, 1, 1),
    requirements=(Requirement(requirement_id="REQ-SOURCE", text="A claim has an accepted evidence assessment"),),
    rule_manifest=(RuleReference(rule_id="RULE-SOURCE", rule_version="1.0"),),
)
rule = Rule(
    rule_id="RULE-SOURCE", rule_version="1.0", policy_id=policy.policy_id,
    policy_version=policy.version, requirement_id="REQ-SOURCE",
    condition=Condition(field="claim.source_recorded", operator=Operator.EQ, value=True),
    claim_id_field="claim.id", expected_result=True,
    evidence_requirement=EvidenceRequirement(minimum_count=1, allowed_source_types=("official",), minimum_quality=70, required_support=Support.DIRECT),
)
evidence = EvidenceRecord(
    evidence_id="E-DEMO-1", claim_id="CLAIM-DEMO-1", source_name="Illustrative official source",
    source_type="official", source_reference="https://example.invalid/reference",
    retrieved_date=date(2026, 10, 20), passage_or_location="Illustrative section; not a real citation",
    access_status=AccessStatus.ACCESSIBLE, quality_score=85,
)
assessment = Assessment(
    assessment_id="A-DEMO-1", evidence_id=evidence.evidence_id, claim_id=evidence.claim_id,
    support=Support.DIRECT, origin=AssessmentOrigin.HUMAN, state=AssessmentState.ACCEPTED,
    assessor_id="demo-reviewer", assessed_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
    rationale="Synthetic assessment used only to exercise the demo flow.",
)
run = ValidationEngine(authorized_assessor_ids={"demo-reviewer"}).run(
    policy, [rule], {"claim": {"source_recorded": True, "id": "CLAIM-DEMO-1"}},
    [evidence], [assessment], date(2026, 10, 21),
)
export_json(run, "output/validation_run.json")
export_audit_csv(run, "output/audit.csv")
export_human_report(run, "output/human_report.txt")
print(f"Demo complete: {run.overall_status.value}")
print("Synthetic data only; no live source was authenticated.")
print("Outputs written to ./output/")
