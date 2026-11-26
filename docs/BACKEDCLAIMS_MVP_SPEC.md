# BackedClaims one-page MVP specification

## Purpose

BackedClaims helps creators identify factual claims that may need evidence before publication. It identifies claims, searches available evidence, shows what supports or contests them, explains why each claim was flagged, and states clearly when evidence is insufficient.

> We verify and contest. We do not judge.

BackedClaims does not decide whether a creator is right or wrong. A source relationship is not a guarantee of truth.

## Customer input and handoff

Customers can submit pasted text, an individual claim, a PDF or other document, and an email address for delivery of the completed audit. They may also provide sources they want considered.

The customer submits material for review. The automated preliminary scan runs as part of intake; the customer does not control the operator's full audit workflow. The customer receives a Preliminary Claim Map, then waits while the operator reviews the evidence and prepares the completed audit.

The immediate customer message should read:

> Your preliminary claim scan is complete. We've identified statements that may benefit from additional verification. Your findings will now undergo human review before your completed BackedClaims audit is returned.

## Claim pipeline

**INGEST → EXTRACT → CLASSIFY → SEARCH → COMPARE → FLAG → CITE → PREVIEW**

Extract statements that are reasonably fact-checkable. Preserve the original copy and mark claim locations in context. The operator can also submit one claim directly.

Initial classifications:

- Financial / Economic
- Historical
- Health / Medical
- Scientific / Technical
- Legal / Regulatory
- Statistical
- Product / Performance
- Attribution / Quotation
- General Factual
- Other Verifiable

Each classification has a consistent highlight color. Color identifies claim type only; it never signals truthfulness or writing quality.

## Preliminary evidence statuses

- **Supported:** Evidence supporting the wording was located.
- **Contested:** Credible evidence challenging or materially complicating the wording was located.
- **Mixed:** Available credible evidence does not point in one clear direction.
- **Source Needed:** The claim could be checked, but sufficient evidence was not located in the sources searched.
- **Insufficient Evidence:** Available evidence is too weak to responsibly support or contest the claim.
- **Not Reasonably Verifiable:** Opinion, prediction, subjective wording, or similar material unsuitable for normal factual verification.

If the system has not actually searched sources, the claim remains unassessed; it must not be labeled Source Needed. Record the search scope when assigning an evidence status.

## Results and operator review

The customer sees their original material with numbered, type-colored claim markers and a Preliminary Claim Map. Selecting a claim shows its classification, preliminary status, why it was flagged, sources and passages when available, and an optional suggested action or rewrite. Suggestions are never mandatory corrections.

The operator sees the same original material beside a numbered checklist. Checking an item records that the operator reviewed it; it does not mean the claim was verified. Selecting an item opens its classification, original statement, preliminary status, reason, evidence, and optional suggested action.

The human reviewer can confirm or reject automated flags, inspect and add sources, preserve conflicting evidence, change classifications or statuses, review suggested wording, and finalize the customer report. Automation cannot override the human-reviewed final state.

## Unsourced claims and evidence integrity

Failure to find evidence must never be converted into a verdict. Use this explanation for Source Needed:

> We couldn't locate sufficient evidence using the sources currently available to us. This does not establish that the claim is true or false.

Never invent sources, citations, evidence, consensus, confidence, or verification results. If a source is unavailable or unreviewed, say so. Allow customers to submit sources that may have been missed.

## Non-negotiable principles

- No evidence does not mean false.
- Supporting evidence does not establish absolute truth.
- Conflicting evidence does not mean the user is wrong.
- Uncertainty is a valid result.
- Keep the customer's original copy intact.
- Explain what was flagged, why, what sources show, and what optional action may help.

## Outside the first release

Credit rewards for customer-submitted sources, customer accounts, and self-service audit controls are later features. The first release is an operator-reviewed service, not a self-service SaaS product.

## Current repository prototype boundary

The checked-in UI is a local front-end concept only. It does not receive customer submissions, extract PDF/DOCX/ZIP contents, run live source search, assign evidence statuses, create a review queue, save operator decisions, or email reports. Its pattern-based claim markers are demonstrations and can miss or misclassify claims. These gaps must be implemented and reviewed before using real customer material.
