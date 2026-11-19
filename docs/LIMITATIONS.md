# Unresolved limitations

This is a review candidate. It has not been frozen or declared production-ready.

## Comparison and verification gaps

- The exact 1.2.0-pre-freeze engine and tests were not recovered. The source comparison is therefore not complete.
- The test suite and demo in this assembled copy were not run during assembly. Follow the commands in the README and inspect the user's terminal output before making any readiness decision.
- The included tests cover named scenarios. Passing them would not prove the absence of other defects or adversarial inputs.

## Trust and evidence limits

- The engine evaluates supplied structured records. It does not authenticate a source, retrieve or preserve original documents, or determine whether a cited passage supports a nuanced claim.
- Evidence quality, source type, reviewer identity, and assessment content depend on a trusted process. The engine cannot defend itself against a compromised backend or fabricated trusted inputs.
- Optional HMAC signatures do not provide identity management, secure key storage, revocation, or a public-key trust system. Anyone with the shared signing key can create a valid signature.
- Perplexity results are discovery candidates, not accepted evidence. Automated tests use local fixtures and do not call the live provider. Its live response shape, current service behavior, data handling, and charges are not validated here.
- URL normalization is not a complete network-fetching security boundary. Any future fetcher must validate resolved addresses and defend against DNS rebinding, redirects, and unsafe file types.
- `APPROVED` means the configured rules passed on the supplied records. It is not a factual guarantee, certification, or expert opinion.

## Product and operational limits

- There is no document intake, claim extraction, original-source retrieval, persistent audit database, immutable storage, user authentication service, or deployment hardening in this package.
- Reports and CSV escaping reduce common presentation risks; they do not make arbitrary downstream spreadsheet or document handling safe in every application.
- The demo uses synthetic records and `example.invalid`, not a real source or customer audit.
