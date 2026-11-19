"""DPP-AUDIT candidate V1 policy/evidence evaluation engine (hardened).

Python 3.12; Pydantic 2.x.

This module evaluates structured records. It does not browse, authenticate sources,
prove that passages support claims, provide expert advice, or secure a web API by itself.
A trusted backend must load authorized policies/rules/assessments and must not accept an
arbitrary EvaluationSnapshot from an untrusted client or AI worker.

"APPROVED" means only: every mandatory rule was satisfied by the records supplied to the
engine. It is NOT a guarantee that any claim is true.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import math
import os
import re
import tempfile
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENGINE_VERSION = "1.1.0-candidate"

CAVEAT = ("Rules satisfied by the supplied records; this is not a guarantee that any claim is true "
          "and does not authenticate sources or replace expert review.")

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}")


def _check_ids(obj: Any, *names: str) -> None:
    """Identifiers must be short, printable and free of newlines/spaces/formula characters."""
    for name in names:
        value = getattr(obj, name)
        if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
            raise ValueError(f"{name} must match [A-Za-z0-9][A-Za-z0-9._:-]{{0,127}}")


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


class ReviewDecisionOutcome(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


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

    @model_validator(mode="after")
    def check_ids(self) -> "Requirement":
        _check_ids(self, "requirement_id")
        return self


class RuleReference(Model):
    rule_id: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def check_ids(self) -> "RuleReference":
        _check_ids(self, "rule_id", "rule_version")
        return self


class Policy(Model):
    policy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: PolicyStatus
    effective_date: date
    requirements: tuple[Requirement, ...] = Field(min_length=1)
    rule_manifest: tuple[RuleReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_policy_ids(self) -> "Policy":
        _check_ids(self, "policy_id", "version")
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
    # Optional: input field holding the claim text; when set, evidence must carry the SHA-256
    # of that exact text so evidence cannot silently be re-used for reworded claims.
    claim_text_field: str | None = None
    # Which condition result counts as a pass. None means True (the original behavior).
    expected_result: Any = None
    mandatory: bool = True
    evidence_requirement: EvidenceRequirement = Field(default_factory=EvidenceRequirement)
    manual_review_required: bool = False

    @model_validator(mode="after")
    def check_fields(self) -> "Rule":
        _check_ids(self, "rule_id", "rule_version", "policy_id", "policy_version", "requirement_id")
        if self.expected_result is not None and not isinstance(self.expected_result, bool):
            raise ValueError("expected_result must be None, True or False")
        return self


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
    # Optional hardening fields (defaults keep older records valid):
    claim_text_sha256: str | None = None          # binds evidence to exact claim wording
    collected_by: str | None = None               # separation of duties vs. the assessor
    requirement_ids: tuple[str, ...] = ()         # empty = usable for any requirement

    @model_validator(mode="after")
    def check_ids(self) -> "EvidenceRecord":
        _check_ids(self, "evidence_id", "claim_id")
        if self.collected_by is not None:
            _check_ids(self, "collected_by")
        for rid in self.requirement_ids:
            if _ID_RE.fullmatch(rid) is None:
                raise ValueError("requirement_ids contains an invalid identifier")
        return self


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
    # Optional hardening fields:
    evidence_sha256: str | None = None            # assessor attests to this exact evidence record
    claim_text_sha256: str | None = None
    signature: str | None = None                  # HMAC-SHA256, see sign_assessment()

    @model_validator(mode="after")
    def prevent_ai_self_acceptance(self) -> "Assessment":
        _check_ids(self, "assessment_id", "evidence_id", "claim_id", "assessor_id")
        if self.assessed_at.tzinfo is None or self.assessed_at.utcoffset() is None:
            raise ValueError("assessed_at must be timezone-aware")
        if self.origin == AssessmentOrigin.AI and self.state == AssessmentState.ACCEPTED:
            raise ValueError("AI-origin assessments cannot be accepted directly")
        return self


class ReviewDecision(Model):
    """A human decision that resolves a manual-review rule. Only authorized reviewers count."""
    decision_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    decision: ReviewDecisionOutcome
    reviewer_id: str = Field(min_length=1)
    decided_at: datetime
    rationale: str = Field(min_length=1)
    signature: str | None = None

    @model_validator(mode="after")
    def check_fields(self) -> "ReviewDecision":
        _check_ids(self, "decision_id", "rule_id", "rule_version", "reviewer_id")
        if self.decided_at.tzinfo is None or self.decided_at.utcoffset() is None:
            raise ValueError("decided_at must be timezone-aware")
        return self


class RuleResult(Model):
    rule_id: str
    rule_version: str
    requirement_id: str
    status: RuleStatus
    reason: str
    evidence_ids: tuple[str, ...] = ()
    assessment_ids: tuple[str, ...] = ()
    decision_ids: tuple[str, ...] = ()
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
    publication_eligibility: PublicationEligibility = PublicationEligibility.ELIGIBLE_FOR_CONSIDERATION
    assessor_allowlist_sha256: str = ""
    warnings: tuple[str, ...] = ()
    caveat: str = CAVEAT
    recorded_at: datetime | None = None
    error: str | None = None


# --------------------------------------------------------------------------- fingerprints

def _jsonable(value: Any) -> Any:
    """Typed canonical form: distinct Python types never collapse into the same JSON."""
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError("mapping keys must be strings for fingerprinting")
            out[k] = _jsonable(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        items = [_jsonable(v) for v in value]
        return {"$set": sorted(items, key=lambda i: json.dumps(i, sort_keys=True))}
    if isinstance(value, (bytes, bytearray)):
        return {"$bytes": bytes(value).hex()}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers are not allowed in fingerprints")
        return value
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise ValueError(f"unsupported type for fingerprinting: {type(value).__name__}")


def canonical_fingerprint(payload: Any) -> str:
    encoded = json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def allowlist_fingerprint(authorized_assessor_ids: Any) -> str:
    return canonical_fingerprint(sorted(authorized_assessor_ids))


def compute_input_fingerprint(*, policy: Policy, rules: Any, input_data: Mapping[str, Any], evidence: Any,
                              assessments: Any, evaluation_date: date, authorized_assessor_ids: Any = (),
                              review_decisions: Any = (), require_signatures: bool = False,
                              keyed_assessor_ids: Any = (), engine_version: str = ENGINE_VERSION) -> str:
    """Public so a verifier can recompute the fingerprint from archived inputs."""
    return canonical_fingerprint({
        "engine_version": engine_version, "policy": policy, "rules": tuple(rules),
        "input_data": input_data, "evidence": tuple(evidence), "assessments": tuple(assessments),
        "review_decisions": tuple(review_decisions), "evaluation_date": evaluation_date,
        "authorized_assessor_ids": sorted(authorized_assessor_ids),
        "keyed_assessor_ids": sorted(keyed_assessor_ids),
        "require_signatures": bool(require_signatures),
    })


def evidence_fingerprint(record: EvidenceRecord) -> str:
    return canonical_fingerprint(record)


def claim_text_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- signatures

def _signing_payload(kind: str, record: BaseModel) -> bytes:
    data = record.model_dump(mode="json")
    data.pop("signature", None)
    return json.dumps({"kind": kind, "record": _jsonable(data)}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_assessment(assessment: Assessment, key: bytes) -> Assessment:
    sig = hmac.new(key, _signing_payload("assessment", assessment), hashlib.sha256).hexdigest()
    return assessment.model_copy(update={"signature": sig})


def sign_review_decision(decision: ReviewDecision, key: bytes) -> ReviewDecision:
    sig = hmac.new(key, _signing_payload("review_decision", decision), hashlib.sha256).hexdigest()
    return decision.model_copy(update={"signature": sig})


def _signature_valid(kind: str, record: BaseModel, key: bytes) -> bool:
    sig = getattr(record, "signature", None)
    if not sig:
        return False
    expected = hmac.new(key, _signing_payload(kind, record), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def publication_eligibility(policy: Policy, publication_date: date) -> PublicationEligibility:
    """Check policy eligibility for a new publication; separate from historical evaluation."""
    if policy.status == PolicyStatus.DRAFT:
        return PublicationEligibility.DRAFT_POLICY
    if policy.status == PolicyStatus.RETIRED:
        return PublicationEligibility.RETIRED_POLICY
    if publication_date < policy.effective_date:
        return PublicationEligibility.NOT_YET_EFFECTIVE
    return PublicationEligibility.ELIGIBLE_FOR_CONSIDERATION


# --------------------------------------------------------------------------- conditions

def _resolve(data: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    """Resolve a dotted path; a literal key that itself contains dots is also honored."""
    if not isinstance(data, Mapping):
        return False, None
    parts = path.split(".")
    for i in range(len(parts), 0, -1):
        key = ".".join(parts[:i])
        if key in data:
            if i == len(parts):
                return True, data[key]
            found, value = _resolve(data[key], ".".join(parts[i:]))
            if found:
                return True, value
    return False, None


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _strict_eq(a: Any, b: Any) -> bool:
    """Type-strict equality: True != 1, "1" != 1; ints and floats compare numerically."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if _is_number(a) and _is_number(b):
        return a == b
    return type(a) is type(b) and a == b


def _ordered(a: Any, b: Any) -> None:
    if _is_number(a) and _is_number(b):
        return
    if isinstance(a, str) and isinstance(b, str):
        return
    if type(a) is type(b) and isinstance(a, (date, datetime)):
        return
    raise TypeError("operands are not comparable")


def _short(value: Any, limit: int = 60) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def evaluate_condition(condition: Condition, data: Mapping[str, Any]) -> tuple[ConditionOutcome, str]:
    exists, actual = _resolve(data, condition.field)
    if condition.operator == Operator.EXISTS:
        if condition.value is not None and not isinstance(condition.value, bool):
            return ConditionOutcome.INVALID, f"exists operator needs a boolean value for {condition.field}"
        expected_exists = True if condition.value is None else condition.value
        result = exists == expected_exists
        return (ConditionOutcome.TRUE if result else ConditionOutcome.FALSE, f"field {condition.field} exists={exists}")
    if not exists:
        return ConditionOutcome.UNKNOWN, f"missing field: {condition.field}"
    try:
        expected = condition.value
        op = condition.operator
        if op == Operator.EQ:
            result = _strict_eq(actual, expected)
        elif op == Operator.NEQ:
            result = not _strict_eq(actual, expected)
        elif op in (Operator.GT, Operator.GTE, Operator.LT, Operator.LTE):
            _ordered(actual, expected)
            result = {Operator.GT: lambda: actual > expected, Operator.GTE: lambda: actual >= expected,
                      Operator.LT: lambda: actual < expected, Operator.LTE: lambda: actual <= expected}[op]()
        elif op == Operator.IN:
            if not isinstance(expected, (list, tuple, set, frozenset)):
                raise TypeError("IN needs a list/tuple/set")
            result = any(_strict_eq(actual, item) for item in expected)
        elif op == Operator.CONTAINS:
            if isinstance(actual, str):
                if not isinstance(expected, str):
                    raise TypeError("CONTAINS on text needs text")
                result = expected in actual
            elif isinstance(actual, (list, tuple)):
                result = any(_strict_eq(item, expected) for item in actual)
            else:
                raise TypeError("CONTAINS needs text or a list")
        else:
            return ConditionOutcome.INVALID, f"unsupported operator: {condition.operator}"
        return (ConditionOutcome.TRUE if bool(result) else ConditionOutcome.FALSE,
                f"{condition.field} {condition.operator.value} {_short(expected)}; actual={_short(actual)}")
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


def _norm_ref(ref: str) -> str:
    """Normalize a source reference so the same source can't be counted twice."""
    text = ref.strip()
    if "://" in text:
        scheme, rest = text.split("://", 1)
        rest = rest.split("#", 1)[0].rstrip("/")
        host, sep, path = rest.partition("/")
        return f"{scheme.lower()}://{host.lower()}{sep}{path}"
    return text.casefold()


class ValidationEngine:
    """Deterministic evaluator. authorized_assessor_ids must come from trusted backend config.

    assessor_keys maps an assessor/reviewer ID to a secret key held by trusted configuration.
    With require_signatures=True an assessment or review decision counts only if its HMAC
    signature verifies and (for assessments) it attests to the exact evidence record.
    """

    def __init__(self, authorized_assessor_ids: set[str] | frozenset[str] = frozenset(), *,
                 assessor_keys: Mapping[str, bytes] | None = None, require_signatures: bool = False):
        self._authorized_assessor_ids = frozenset(authorized_assessor_ids)
        self._keys = dict(assessor_keys or {})
        self._require_signatures = bool(require_signatures)

    # -- trust checks -----------------------------------------------------------------
    def _signature_problem(self, kind: str, record: BaseModel, actor_id: str) -> str | None:
        key = self._keys.get(actor_id)
        if self._require_signatures and key is None:
            return "no signing key configured for this actor"
        if key is not None:
            if getattr(record, "signature", None) is None:
                if self._require_signatures:
                    return "signature required but missing"
            elif not _signature_valid(kind, record, key):
                return "signature invalid"
        return None

    def _assessment_problem(self, a: Assessment, ev: EvidenceRecord, evaluation_date: date,
                            claim_text_hash: str | None) -> str | None:
        if a.state != AssessmentState.ACCEPTED:
            return "not accepted"
        if a.origin not in {AssessmentOrigin.HUMAN, AssessmentOrigin.DETERMINISTIC_CHECK}:
            return "origin cannot satisfy evidence"
        if a.assessor_id not in self._authorized_assessor_ids:
            return "assessor not authorized"
        if a.assessed_at.astimezone(timezone.utc).date() > evaluation_date:
            return "assessed after the evaluation date"
        if ev.collected_by is not None and ev.collected_by == a.assessor_id:
            return "assessor also collected the evidence"
        if a.evidence_sha256 is not None and a.evidence_sha256 != evidence_fingerprint(ev):
            return "evidence changed since it was assessed"
        if self._require_signatures and a.evidence_sha256 is None:
            return "evidence attestation (evidence_sha256) required"
        if claim_text_hash is not None and a.claim_text_sha256 is not None and a.claim_text_sha256 != claim_text_hash:
            return "claim text changed since it was assessed"
        problem = self._signature_problem("assessment", a, a.assessor_id)
        return problem

    # -- main run -----------------------------------------------------------------------
    def run(
        self,
        policy: Policy,
        rules: tuple[Rule, ...] | list[Rule],
        input_data: Mapping[str, Any],
        evidence: tuple[EvidenceRecord, ...] | list[EvidenceRecord],
        assessments: tuple[Assessment, ...] | list[Assessment],
        evaluation_date: date,
        review_decisions: tuple[ReviewDecision, ...] | list[ReviewDecision] = (),
        recorded_at: datetime | None = None,
    ) -> ValidationRun:
        rules, evidence, assessments = tuple(rules), tuple(evidence), tuple(assessments)
        review_decisions = tuple(review_decisions)
        validate_traceability(policy, rules)
        evidence_ids = [e.evidence_id for e in evidence]
        assessment_ids = [a.assessment_id for a in assessments]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("duplicate evidence IDs")
        if len(assessment_ids) != len(set(assessment_ids)):
            raise ValueError("duplicate assessment IDs")
        decision_ids = [d.decision_id for d in review_decisions]
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("duplicate review decision IDs")
        rule_keys = {(r.rule_id, r.rule_version) for r in rules}
        for d in review_decisions:
            if (d.rule_id, d.rule_version) not in rule_keys:
                raise ValueError(f"review decision {d.decision_id} references unknown rule")
        evidence_by_id = {e.evidence_id: e for e in evidence}
        for assessment in assessments:
            record = evidence_by_id.get(assessment.evidence_id)
            if record is None:
                raise ValueError(f"assessment {assessment.assessment_id} references missing evidence")
            if record.claim_id != assessment.claim_id:
                raise ValueError(f"assessment {assessment.assessment_id} claim/evidence mismatch")

        # Fingerprint first: unsupported/non-finite input fails before any decision is made.
        fingerprint = compute_input_fingerprint(
            policy=policy, rules=rules, input_data=input_data, evidence=evidence, assessments=assessments,
            evaluation_date=evaluation_date, authorized_assessor_ids=self._authorized_assessor_ids,
            review_decisions=review_decisions, require_signatures=self._require_signatures,
            keyed_assessor_ids=self._keys.keys())

        eligibility = publication_eligibility(policy, evaluation_date)
        results: list[RuleResult] = []
        trail = [f"engine={ENGINE_VERSION}", f"policy={policy.policy_id}@{policy.version}",
                 f"evaluation_date={evaluation_date.isoformat()}",
                 f"policy_status={policy.status.value}", f"publication_eligibility={eligibility.value}",
                 f"authorized_assessors={len(self._authorized_assessor_ids)}",
                 f"require_signatures={self._require_signatures}"]
        ignored: dict[str, str] = {}
        linked_assessment_ids: set[str] = set()

        for rule in sorted(rules, key=lambda r: r.rule_id):
            if rule.manual_review_required or rule.condition is None:
                result = self._manual_review_result(rule, review_decisions, evaluation_date, trail)
                results.append(result)
                trail.append(f"{rule.rule_id}@{rule.rule_version}:{result.status.value}")
                continue

            outcome, reason = evaluate_condition(rule.condition, input_data)
            missing: tuple[str, ...] = ()
            if outcome in (ConditionOutcome.INVALID, ConditionOutcome.UNKNOWN):
                status = RuleStatus.INDETERMINATE
                missing = (reason,)
            else:
                expected = True if rule.expected_result is None else rule.expected_result
                status = RuleStatus.PASS if (outcome == ConditionOutcome.TRUE) == expected else RuleStatus.FAIL

            linked_evidence: list[EvidenceRecord] = []
            linked_assessments: list[Assessment] = []
            claim_text_hash: str | None = None
            needs_evidence = rule.evidence_requirement.minimum_count > 0
            if rule.claim_id_field:
                found, claim_value = _resolve(input_data, rule.claim_id_field)
                if not found or not isinstance(claim_value, str) or not claim_value:
                    if needs_evidence and status == RuleStatus.PASS:
                        status = RuleStatus.INDETERMINATE
                        missing = (f"missing or invalid claim identifier field: {rule.claim_id_field}",)
                else:
                    linked_evidence = [e for e in evidence if e.claim_id == claim_value
                                       and (not e.requirement_ids or rule.requirement_id in e.requirement_ids)]
                    linked_ids = {e.evidence_id for e in linked_evidence}
                    linked_assessments = [a for a in assessments if a.claim_id == claim_value and a.evidence_id in linked_ids]
            elif needs_evidence:
                status = RuleStatus.INDETERMINATE
                missing = ("rule requires evidence but has no claim_id_field",)

            if rule.claim_text_field and status == RuleStatus.PASS and needs_evidence:
                found_t, text_value = _resolve(input_data, rule.claim_text_field)
                if not found_t or not isinstance(text_value, str) or not text_value:
                    status = RuleStatus.INDETERMINATE
                    missing = (f"missing or invalid claim text field: {rule.claim_text_field}",)
                else:
                    claim_text_hash = claim_text_fingerprint(text_value)

            evidence_for_result = sorted({e.evidence_id for e in linked_evidence})
            assessments_for_result = sorted({a.assessment_id for a in linked_assessments})
            linked_assessment_ids.update(assessments_for_result)

            if status == RuleStatus.PASS and needs_evidence:
                req = rule.evidence_requirement
                accepted: dict[str, list[Assessment]] = {}
                for a in linked_assessments:
                    problem = self._assessment_problem(a, evidence_by_id[a.evidence_id], evaluation_date, claim_text_hash)
                    if problem is None:
                        accepted.setdefault(a.evidence_id, []).append(a)
                    else:
                        ignored.setdefault(a.assessment_id, problem)
                concerns: list[str] = []
                for ev in linked_evidence:
                    acc = accepted.get(ev.evidence_id, [])
                    supports = {a.support for a in acc}
                    if ev.access_status == AccessStatus.INACCESSIBLE:
                        concerns.append(f"evidence {ev.evidence_id} inaccessible")
                    bad = supports & {Support.CONTRADICTED, Support.OUTDATED, Support.EXPERT_REVIEW}
                    if bad:
                        concerns.append(f"evidence {ev.evidence_id} requires review: " + ",".join(sorted(s.value for s in bad)))
                    elif len(supports) > 1:
                        concerns.append(f"evidence {ev.evidence_id} has conflicting assessments: " + ",".join(sorted(s.value for s in supports)))
                    if claim_text_hash is not None and ev.claim_text_sha256 is not None and ev.claim_text_sha256 != claim_text_hash:
                        concerns.append(f"evidence {ev.evidence_id} was recorded for different claim wording")
                if concerns:
                    status = RuleStatus.REVIEW_REQUIRED
                    missing = tuple(concerns)
                else:
                    suitable: list[EvidenceRecord] = []
                    notes: list[str] = []
                    for ev in linked_evidence:
                        acc = accepted.get(ev.evidence_id, [])
                        if not acc:
                            continue
                        if ev.quality_score < req.minimum_quality:
                            continue
                        if req.allowed_source_types and ev.source_type not in req.allowed_source_types:
                            continue
                        if {a.support for a in acc} != {req.required_support}:
                            continue
                        if claim_text_hash is not None and ev.claim_text_sha256 is None:
                            notes.append(f"evidence {ev.evidence_id} has no claim text hash")
                            continue
                        if req.maximum_age_days is not None:
                            age = (evaluation_date - ev.retrieved_date).days
                            if age < 0 or age > req.maximum_age_days:
                                continue
                            if ev.published_date is None:
                                notes.append(f"evidence {ev.evidence_id} has no published_date for the age limit")
                                continue
                            pub_age = (evaluation_date - ev.published_date).days
                            if pub_age < 0 or pub_age > req.maximum_age_days:
                                notes.append(f"evidence {ev.evidence_id} published too long ago or after the evaluation date")
                                continue
                        suitable.append(ev)
                    distinct_sources = {_norm_ref(e.source_reference) for e in suitable}
                    if len(distinct_sources) < req.minimum_count:
                        status = RuleStatus.INDETERMINATE
                        missing = (f"sufficient accepted evidence not established: {len(distinct_sources)}/{req.minimum_count} distinct sources",) + tuple(notes)

            results.append(RuleResult(rule_id=rule.rule_id, rule_version=rule.rule_version,
                requirement_id=rule.requirement_id, status=status, reason=reason,
                evidence_ids=tuple(evidence_for_result), assessment_ids=tuple(assessments_for_result),
                missing_information=tuple(missing)))
            trail.append(f"{rule.rule_id}@{rule.rule_version}:{status.value}")

        for a in assessments:
            if a.assessment_id not in linked_assessment_ids:
                ignored.setdefault(a.assessment_id, "not linked to any evaluated rule")
        for aid in sorted(ignored):
            trail.append(f"assessment {aid} ignored: {ignored[aid]}")

        overall = self._aggregate(results, rules)
        if policy.status == PolicyStatus.DRAFT and overall == OverallStatus.APPROVED:
            overall = OverallStatus.REVIEW_REQUIRED
            trail.append("draft policy cannot be APPROVED; downgraded to review_required")
        mandatory = {r.rule_id for r in rules if r.mandatory}
        warnings = tuple(f"non-mandatory rule {r.rule_id} is {r.status.value}" for r in results
                         if r.rule_id not in mandatory and r.status not in {RuleStatus.PASS, RuleStatus.NOT_APPLICABLE})
        return ValidationRun(engine_version=ENGINE_VERSION, policy_id=policy.policy_id,
            policy_version=policy.version, evaluation_date=evaluation_date,
            input_fingerprint=fingerprint, overall_status=overall,
            rule_results=tuple(results), audit_trail=tuple(trail),
            publication_eligibility=eligibility,
            assessor_allowlist_sha256=allowlist_fingerprint(self._authorized_assessor_ids),
            warnings=warnings, recorded_at=recorded_at)

    def run_safe(self, policy: Policy, rules: Any, input_data: Mapping[str, Any], evidence: Any,
                 assessments: Any, evaluation_date: date, review_decisions: Any = (),
                 recorded_at: datetime | None = None) -> ValidationRun:
        """Like run(), but a failure yields an INDETERMINATE run record instead of an exception."""
        try:
            return self.run(policy, rules, input_data, evidence, assessments, evaluation_date,
                            review_decisions, recorded_at)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            message = f"{type(exc).__name__}: {exc}"[:300]
            return ValidationRun(engine_version=ENGINE_VERSION, policy_id=policy.policy_id,
                policy_version=policy.version, evaluation_date=evaluation_date,
                input_fingerprint="UNAVAILABLE", overall_status=OverallStatus.INDETERMINATE,
                rule_results=(), audit_trail=(f"engine={ENGINE_VERSION}", f"run failed: {message}"),
                publication_eligibility=publication_eligibility(policy, evaluation_date),
                assessor_allowlist_sha256=allowlist_fingerprint(self._authorized_assessor_ids),
                recorded_at=recorded_at, error=message)

    def _manual_review_result(self, rule: Rule, decisions: tuple[ReviewDecision, ...],
                              evaluation_date: date, trail: list[str]) -> RuleResult:
        valid: list[ReviewDecision] = []
        for d in decisions:
            if (d.rule_id, d.rule_version) != (rule.rule_id, rule.rule_version):
                continue
            problem = None
            if d.reviewer_id not in self._authorized_assessor_ids:
                problem = "reviewer not authorized"
            elif d.decided_at.astimezone(timezone.utc).date() > evaluation_date:
                problem = "decided after the evaluation date"
            else:
                problem = self._signature_problem("review_decision", d, d.reviewer_id)
            if problem:
                trail.append(f"review decision {d.decision_id} ignored: {problem}")
            else:
                valid.append(d)
        base = dict(rule_id=rule.rule_id, rule_version=rule.rule_version, requirement_id=rule.requirement_id)
        ids = tuple(sorted(d.decision_id for d in valid))
        outcomes = {d.decision for d in valid}
        if len(outcomes) == 1:
            outcome = next(iter(outcomes))
            status = RuleStatus.PASS if outcome == ReviewDecisionOutcome.APPROVED else RuleStatus.FAIL
            return RuleResult(**base, status=status, reason=f"human review decision: {outcome.value}", decision_ids=ids)
        if len(outcomes) > 1:
            return RuleResult(**base, status=RuleStatus.REVIEW_REQUIRED, reason="conflicting review decisions",
                              decision_ids=ids, missing_information=("conflicting review decisions",))
        return RuleResult(**base, status=RuleStatus.REVIEW_REQUIRED, reason="rule requires human review")

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


# --------------------------------------------------------------------------- exports

_CTRL_RE = re.compile(r"[\x00-\x1f\x7f\u2028\u2029]")


def _clean(text: Any) -> str:
    """Make free text safe for single-line report/CSV cells (no forged lines)."""
    return _CTRL_RE.sub(" ", str(text))


def _csv_safe(text: Any) -> str:
    cell = _clean(text)
    return "'" + cell if cell[:1] in ("=", "+", "-", "@") else cell


def _atomic_write(path: str, write) -> str:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(out.parent), prefix=".tmp-", suffix=out.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            write(handle)
        os.replace(tmp, out)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return str(out)


def export_json(run: ValidationRun, path: str) -> str:
    return _atomic_write(path, lambda h: h.write(run.model_dump_json(indent=2)))


_CSV_FIELDS = [
    "engine_version", "policy_id", "policy_version", "evaluation_date",
    "input_fingerprint", "assessor_allowlist_sha256", "publication_eligibility",
    "overall_status", "caveat", "rule_id", "rule_version",
    "requirement_id", "status", "reason", "evidence_ids", "assessment_ids", "decision_ids",
    "missing_information", "warnings",
]


def export_audit_csv(run: ValidationRun, path: str) -> str:
    """Export one row per rule result; this is an audit trail, not source validation."""
    def write(handle):
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for result in run.rule_results:
            row = {
                "engine_version": run.engine_version, "policy_id": run.policy_id,
                "policy_version": run.policy_version, "evaluation_date": run.evaluation_date.isoformat(),
                "input_fingerprint": run.input_fingerprint,
                "assessor_allowlist_sha256": run.assessor_allowlist_sha256,
                "publication_eligibility": run.publication_eligibility.value,
                "overall_status": run.overall_status.value, "caveat": run.caveat,
                "rule_id": result.rule_id, "rule_version": result.rule_version,
                "requirement_id": result.requirement_id, "status": result.status.value,
                "reason": result.reason, "evidence_ids": ";".join(result.evidence_ids),
                "assessment_ids": ";".join(result.assessment_ids),
                "decision_ids": ";".join(result.decision_ids),
                "missing_information": ";".join(result.missing_information),
                "warnings": ";".join(run.warnings),
            }
            writer.writerow({k: _csv_safe(v) for k, v in row.items()})
    return _atomic_write(path, write)


def human_report(run: ValidationRun) -> str:
    """Render a concise factual report from the deterministic run record."""
    lines = [
        "DPP-AUDIT VALIDATION REPORT",
        "===========================",
        f"Overall status: {run.overall_status.value.upper()} (rules-based result; not a truth guarantee)",
        f"Caveat: {_clean(run.caveat)}",
        f"Engine version: {_clean(run.engine_version)}",
        f"Policy: {_clean(run.policy_id)} v{_clean(run.policy_version)}",
        f"Publication eligibility: {run.publication_eligibility.value}",
        f"Evaluation date: {run.evaluation_date.isoformat()}",
        f"Input fingerprint (SHA-256): {_clean(run.input_fingerprint)}",
        f"Assessor allowlist fingerprint (SHA-256): {_clean(run.assessor_allowlist_sha256)}",
    ]
    if run.error:
        lines.append(f"Run error: {_clean(run.error)}")
    lines += ["", "Rule findings:"]
    for result in run.rule_results:
        lines.extend([
            f"- {_clean(result.rule_id)} v{_clean(result.rule_version)} [{result.status.value.upper()}]",
            f"  Requirement: {_clean(result.requirement_id)}",
            f"  Reason: {_clean(result.reason)}",
        ])
        if result.evidence_ids:
            lines.append(f"  Evidence records: {_clean(', '.join(result.evidence_ids))}")
        if result.assessment_ids:
            lines.append(f"  Assessments: {_clean(', '.join(result.assessment_ids))}")
        if result.decision_ids:
            lines.append(f"  Review decisions: {_clean(', '.join(result.decision_ids))}")
        if result.missing_information:
            lines.append(f"  Missing/review information: {_clean('; '.join(result.missing_information))}")
    if run.warnings:
        lines += ["", "Warnings:"] + [f"- {_clean(w)}" for w in run.warnings]
    ignored = [t for t in run.audit_trail if " ignored: " in t]
    if ignored:
        lines += ["", "Records ignored:"] + [f"- {_clean(t)}" for t in ignored]
    lines.extend([
        "",
        "Scope limitation:",
        "This report records structured rule evaluation. It does not by itself authenticate sources,",
        "prove that quoted passages support claims, or replace expert review.",
    ])
    return "\n".join(lines) + "\n"


def export_human_report(run: ValidationRun, path: str) -> str:
    return _atomic_write(path, lambda h: h.write(human_report(run)))
