"""DPP-AUDIT candidate V1 policy/evidence evaluation engine.

Python 3.12; Pydantic 2.x.

This module evaluates structured records. It does not browse, authenticate sources,
prove that passages support claims, provide expert advice, or secure a web API by itself.
A trusted backend must load authorized policies/rules/assessments and must not accept an
arbitrary EvaluationSnapshot from an untrusted client or AI worker.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENGINE_VERSION = "1.0.0-candidate"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class PolicyStatus(str, Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    RETIRED = "retired"


class Operator(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    CONTAINS = "contains"
    EXISTS = "exists"


class ConditionOutcome(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"
    INVALID = "invalid"


class Support(str, Enum):
    DIRECT = "direct"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    OUTDATED = "outdated"
    UNCLEAR = "unclear"
    EXPERT_REVIEW = "expert_review"


class AccessStatus(str, Enum):
    ACCESSIBLE = "accessible"
    INACCESSIBLE = "inaccessible"


class AssessmentOrigin(str, Enum):
    AI = "ai"
    HUMAN = "human"
    DETERMINISTIC_CHECK = "deterministic_check"


class AssessmentState(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"


class RuleStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INDETERMINATE = "indeterminate"
    REVIEW_REQUIRED = "review_required"
    NOT_APPLICABLE = "not_applicable"


class OverallStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REVIEW_REQUIRED = "review_required"
    INDETERMINATE = "indeterminate"


class PublicationEligibility(str, Enum):
    ELIGIBLE_FOR_CONSIDERATION = "eligible_for_consideration"
    NOT_YET_EFFECTIVE = "not_yet_effective"
    DRAFT_POLICY = "draft_policy"
    RETIRED_POLICY = "retired_policy"


class Requirement(Model):
    requirement_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    mandatory: bool = True
    manual_review_only: bool = False


class RuleReference(Model):
    rule_id: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)


class Policy(Model):
    policy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: PolicyStatus
    effective_date: date
    requirements: tuple[Requirement, ...] = Field(min_length=1)
    rule_manifest: tuple[RuleReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_policy_ids(self) -> "Policy":
        req_ids = [r.requirement_id for r in self.requirements]
        if len(req_ids) != len(set(req_ids)):
            raise ValueError("duplicate requirement IDs")
        manifest_ids = [r.rule_id for r in self.rule_manifest]
        if len(manifest_ids) != len(set(manifest_ids)):
            raise ValueError("duplicate rule IDs in policy manifest")
        return self


class Condition(Model):
    field: str = Field(min_length=1)
    operator: Operator
    value: Any = None


class EvidenceRequirement(Model):
    minimum_count: int = Field(default=0, ge=0)
    allowed_source_types: tuple[str, ...] = ()
    minimum_quality: int = Field(default=0, ge=0, le=100)
    required_support: Support = Support.DIRECT
    maximum_age_days: int | None = Field(default=None, ge=0)


class Rule(Model):
    rule_id: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    condition: Condition | None
    claim_id_field: str | None = None
    expected_result: Any = None
    mandatory: bool = True
    evidence_requirement: EvidenceRequirement = Field(default_factory=EvidenceRequirement)
    manual_review_required: bool = False


class EvidenceRecord(Model):
    evidence_id: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    retrieved_date: date
    published_date: date | None = None
    passage_or_location: str = Field(min_length=1)
    access_status: AccessStatus
    quality_score: int = Field(ge=0, le=100)


class Assessment(Model):
    assessment_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    support: Support
    origin: AssessmentOrigin
    state: AssessmentState
    assessor_id: str = Field(min_length=1)
    assessed_at: datetime
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def prevent_ai_self_acceptance(self) -> "Assessment":
        if self.origin == AssessmentOrigin.AI and self.state == AssessmentState.ACCEPTED:
            raise ValueError("AI-origin assessments cannot be accepted directly")
        return self


class RuleResult(Model):
    rule_id: str
    rule_version: str
    requirement_id: str
    status: RuleStatus
    reason: str
    evidence_ids: tuple[str, ...] = ()
    assessment_ids: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()


class ValidationRun(Model):
    engine_version: str
    policy_id: str
    policy_version: str
    evaluation_date: date
    input_fingerprint: str
    overall_status: OverallStatus
    rule_results: tuple[RuleResult, ...]
    audit_trail: tuple[str, ...]


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numbers are not allowed in fingerprints")
    return value


def canonical_fingerprint(payload: Any) -> str:
    encoded = json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def publication_eligibility(policy: Policy, publication_date: date) -> PublicationEligibility:
    """Check policy eligibility for a new publication; separate from historical evaluation."""
    if policy.status == PolicyStatus.DRAFT:
        return PublicationEligibility.DRAFT_POLICY
    if policy.status == PolicyStatus.RETIRED:
        return PublicationEligibility.RETIRED_POLICY
    if publication_date < policy.effective_date:
        return PublicationEligibility.NOT_YET_EFFECTIVE
    return PublicationEligibility.ELIGIBLE_FOR_CONSIDERATION


def _resolve(data: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def evaluate_condition(condition: Condition, data: Mapping[str, Any]) -> tuple[ConditionOutcome, str]:
    exists, actual = _resolve(data, condition.field)
    if condition.operator == Operator.EXISTS:
        expected_exists = True if condition.value is None else bool(condition.value)
        result = exists == expected_exists
        return (ConditionOutcome.TRUE if result else ConditionOutcome.FALSE, f"field {condition.field} exists={exists}")
    if not exists:
        return ConditionOutcome.UNKNOWN, f"missing field: {condition.field}"
    try:
        expected = condition.value
        if condition.operator == Operator.EQ:
            result = actual == expected
        elif condition.operator == Operator.NEQ:
            result = actual != expected
        elif condition.operator == Operator.GT:
            result = actual > expected
        elif condition.operator == Operator.GTE:
            result = actual >= expected
        elif condition.operator == Operator.LT:
            result = actual < expected
        elif condition.operator == Operator.LTE:
            result = actual <= expected
        elif condition.operator == Operator.IN:
            result = actual in expected
        elif condition.operator == Operator.CONTAINS:
            result = expected in actual
        else:
            return ConditionOutcome.INVALID, f"unsupported operator: {condition.operator}"
        return (ConditionOutcome.TRUE if bool(result) else ConditionOutcome.FALSE,
                f"{condition.field} {condition.operator.value} {expected!r}; actual={actual!r}")
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        return ConditionOutcome.INVALID, f"invalid comparison for {condition.field}: {type(exc).__name__}"


def validate_traceability(policy: Policy, rules: tuple[Rule, ...] | list[Rule]) -> None:
    rules = tuple(rules)
    ids = [r.rule_id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate rule IDs")
    manifest = {(r.rule_id, r.rule_version) for r in policy.rule_manifest}
    actual_manifest = {(r.rule_id, r.rule_version) for r in rules}
    if manifest != actual_manifest:
        raise ValueError("supplied rules do not exactly match policy rule manifest")
    reqs = {r.requirement_id: r for r in policy.requirements}
    for rule in rules:
        if rule.policy_id != policy.policy_id or rule.policy_version != policy.version:
            raise ValueError(f"rule {rule.rule_id} policy linkage mismatch")
        requirement = reqs.get(rule.requirement_id)
        if requirement is None:
            raise ValueError(f"orphan rule: {rule.rule_id}")
        if rule.mandatory != requirement.mandatory:
            raise ValueError(f"rule {rule.rule_id} mandatory flag mismatch")
        if requirement.manual_review_only and not rule.manual_review_required:
            raise ValueError(f"rule {rule.rule_id} must require manual review")
        if rule.condition is None and not rule.manual_review_required:
            raise ValueError(f"rule {rule.rule_id} has no condition and no manual review")
    covered = {r.requirement_id for r in rules}
    uncovered = {r.requirement_id for r in policy.requirements} - covered
    if uncovered:
        raise ValueError(f"requirements without rules: {sorted(uncovered)}")


class ValidationEngine:
    """Deterministic evaluator. authorized_assessor_ids must come from trusted backend config."""
    def __init__(self, authorized_assessor_ids: set[str] | frozenset[str] = frozenset()):
        self._authorized_assessor_ids = frozenset(authorized_assessor_ids)

    def run(
        self,
        policy: Policy,
        rules: tuple[Rule, ...] | list[Rule],
        input_data: Mapping[str, Any],
        evidence: tuple[EvidenceRecord, ...] | list[EvidenceRecord],
        assessments: tuple[Assessment, ...] | list[Assessment],
        evaluation_date: date,
    ) -> ValidationRun:
        rules, evidence, assessments = tuple(rules), tuple(evidence), tuple(assessments)
        validate_traceability(policy, rules)
        evidence_ids = [e.evidence_id for e in evidence]
        assessment_ids = [a.assessment_id for a in assessments]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("duplicate evidence IDs")
        if len(assessment_ids) != len(set(assessment_ids)):
            raise ValueError("duplicate assessment IDs")
        evidence_by_id = {e.evidence_id: e for e in evidence}
        for assessment in assessments:
            record = evidence_by_id.get(assessment.evidence_id)
            if record is None:
                raise ValueError(f"assessment {assessment.assessment_id} references missing evidence")
            if record.claim_id != assessment.claim_id:
                raise ValueError(f"assessment {assessment.assessment_id} claim/evidence mismatch")

        results: list[RuleResult] = []
        trail = [f"engine={ENGINE_VERSION}", f"policy={policy.policy_id}@{policy.version}", f"evaluation_date={evaluation_date.isoformat()}"]
        for rule in sorted(rules, key=lambda r: r.rule_id):
            if rule.manual_review_required or rule.condition is None:
                results.append(RuleResult(rule_id=rule.rule_id, rule_version=rule.rule_version,
                    requirement_id=rule.requirement_id, status=RuleStatus.REVIEW_REQUIRED,
                    reason="rule requires human review"))
                continue

            outcome, reason = evaluate_condition(rule.condition, input_data)
            if outcome == ConditionOutcome.INVALID:
                status = RuleStatus.INDETERMINATE
                missing = (reason,)
            elif outcome == ConditionOutcome.UNKNOWN:
                status = RuleStatus.INDETERMINATE
                missing = (reason,)
            elif outcome == ConditionOutcome.FALSE:
                status = RuleStatus.FAIL
                missing = ()
            else:
                status = RuleStatus.PASS
                missing = ()

            linked_evidence: list[EvidenceRecord] = []
            linked_assessments: list[Assessment] = []
            if rule.claim_id_field:
                found, claim_value = _resolve(input_data, rule.claim_id_field)
                if not found or not isinstance(claim_value, str) or not claim_value:
                    if rule.evidence_requirement.minimum_count > 0 and status == RuleStatus.PASS:
                        status = RuleStatus.INDETERMINATE
                        missing = (f"missing or invalid claim identifier field: {rule.claim_id_field}",)
                else:
                    linked_evidence = [e for e in evidence if e.claim_id == claim_value]
                    linked_assessments = [a for a in assessments if a.claim_id == claim_value]
            elif rule.evidence_requirement.minimum_count > 0:
                status = RuleStatus.INDETERMINATE
                missing = ("rule requires evidence but has no claim_id_field",)
            evidence_for_result = sorted({e.evidence_id for e in linked_evidence})
            assessments_for_result = sorted({a.assessment_id for a in linked_assessments})

            if status == RuleStatus.PASS and rule.evidence_requirement.minimum_count > 0:
                support_assessments = [a for a in linked_assessments if a.state == AssessmentState.ACCEPTED and a.assessor_id in self._authorized_assessor_ids and a.origin in {AssessmentOrigin.HUMAN, AssessmentOrigin.DETERMINISTIC_CHECK}]
                assessments_by_evidence = {a.evidence_id: a for a in support_assessments}
                concerns: list[str] = []
                for ev in linked_evidence:
                    assessment = assessments_by_evidence.get(ev.evidence_id)
                    if ev.access_status == AccessStatus.INACCESSIBLE:
                        concerns.append(f"evidence {ev.evidence_id} inaccessible")
                    elif assessment and assessment.support in {Support.CONTRADICTED, Support.OUTDATED, Support.EXPERT_REVIEW}:
                        concerns.append(f"evidence {ev.evidence_id} requires review: {assessment.support.value}")
                if concerns:
                    status = RuleStatus.REVIEW_REQUIRED
                    missing = tuple(concerns)
                else:
                    suitable = []
                    for ev in linked_evidence:
                        assessment = assessments_by_evidence.get(ev.evidence_id)
                        if not assessment:
                            continue
                        if ev.quality_score < rule.evidence_requirement.minimum_quality:
                            continue
                        if rule.evidence_requirement.allowed_source_types and ev.source_type not in rule.evidence_requirement.allowed_source_types:
                            continue
                        if assessment.support != rule.evidence_requirement.required_support:
                            continue
                        if rule.evidence_requirement.maximum_age_days is not None:
                            age = (evaluation_date - ev.retrieved_date).days
                            if age < 0 or age > rule.evidence_requirement.maximum_age_days:
                                continue
                        suitable.append(ev)
                    if len(suitable) < rule.evidence_requirement.minimum_count:
                        status = RuleStatus.INDETERMINATE
                        missing = (f"sufficient accepted evidence not established: {len(suitable)}/{rule.evidence_requirement.minimum_count}",)

            results.append(RuleResult(rule_id=rule.rule_id, rule_version=rule.rule_version,
                requirement_id=rule.requirement_id, status=status, reason=reason,
                evidence_ids=tuple(evidence_for_result), assessment_ids=tuple(assessments_for_result),
                missing_information=tuple(missing)))
            trail.append(f"{rule.rule_id}@{rule.rule_version}:{status.value}")

        overall = self._aggregate(results, rules)
        payload = {"engine_version": ENGINE_VERSION, "policy": policy, "rules": rules,
                   "input_data": input_data, "evidence": evidence, "assessments": assessments,
                   "evaluation_date": evaluation_date}
        return ValidationRun(engine_version=ENGINE_VERSION, policy_id=policy.policy_id,
            policy_version=policy.version, evaluation_date=evaluation_date,
            input_fingerprint=canonical_fingerprint(payload), overall_status=overall,
            rule_results=tuple(results), audit_trail=tuple(trail))

    @staticmethod
    def _aggregate(results: list[RuleResult], rules: tuple[Rule, ...]) -> OverallStatus:
        by_id = {r.rule_id: r for r in results}
        mandatory_ids = {r.rule_id for r in rules if r.mandatory}
        if not mandatory_ids or not mandatory_ids.issubset(by_id):
            return OverallStatus.INDETERMINATE
        mandatory_results = [by_id[rid] for rid in mandatory_ids]
        if any(r.status == RuleStatus.FAIL for r in mandatory_results):
            return OverallStatus.REJECTED
        if any(r.status == RuleStatus.REVIEW_REQUIRED for r in mandatory_results):
            return OverallStatus.REVIEW_REQUIRED
        if any(r.status == RuleStatus.INDETERMINATE for r in mandatory_results):
            return OverallStatus.INDETERMINATE
        if all(r.status in {RuleStatus.PASS, RuleStatus.NOT_APPLICABLE} for r in mandatory_results):
            return OverallStatus.APPROVED
        return OverallStatus.INDETERMINATE


def export_json(run: ValidationRun, path: str) -> str:
    from pathlib import Path
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return str(out)


def export_audit_csv(run: ValidationRun, path: str) -> str:
    """Export one row per rule result; this is an audit trail, not source validation."""
    import csv
    from pathlib import Path
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "engine_version", "policy_id", "policy_version", "evaluation_date",
            "input_fingerprint", "overall_status", "rule_id", "rule_version",
            "requirement_id", "status", "reason", "evidence_ids", "assessment_ids",
            "missing_information",
        ])
        writer.writeheader()
        for result in run.rule_results:
            writer.writerow({
                "engine_version": run.engine_version,
                "policy_id": run.policy_id,
                "policy_version": run.policy_version,
                "evaluation_date": run.evaluation_date.isoformat(),
                "input_fingerprint": run.input_fingerprint,
                "overall_status": run.overall_status.value,
                "rule_id": result.rule_id,
                "rule_version": result.rule_version,
                "requirement_id": result.requirement_id,
                "status": result.status.value,
                "reason": result.reason,
                "evidence_ids": ";".join(result.evidence_ids),
                "assessment_ids": ";".join(result.assessment_ids),
                "missing_information": ";".join(result.missing_information),
            })
    return str(out)


def human_report(run: ValidationRun) -> str:
    """Render a concise factual report from the deterministic run record."""
    lines = [
        "DPP-AUDIT VALIDATION REPORT",
        "===========================",
        f"Overall status: {run.overall_status.value.upper()}",
        f"Engine version: {run.engine_version}",
        f"Policy: {run.policy_id} v{run.policy_version}",
        f"Evaluation date: {run.evaluation_date.isoformat()}",
        f"Input fingerprint (SHA-256): {run.input_fingerprint}",
        "",
        "Rule findings:",
    ]
    for result in run.rule_results:
        lines.extend([
            f"- {result.rule_id} v{result.rule_version} [{result.status.value.upper()}]",
            f"  Requirement: {result.requirement_id}",
            f"  Reason: {result.reason}",
        ])
        if result.evidence_ids:
            lines.append(f"  Evidence records: {', '.join(result.evidence_ids)}")
        if result.assessment_ids:
            lines.append(f"  Assessments: {', '.join(result.assessment_ids)}")
        if result.missing_information:
            lines.append(f"  Missing/review information: {'; '.join(result.missing_information)}")
    lines.extend([
        "",
        "Scope limitation:",
        "This report records structured rule evaluation. It does not by itself authenticate sources,",
        "prove that quoted passages support claims, or replace expert review.",
    ])
    return "\n".join(lines) + "\n"


def export_human_report(run: ValidationRun, path: str) -> str:
    from pathlib import Path
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(human_report(run), encoding="utf-8")
    return str(out)
