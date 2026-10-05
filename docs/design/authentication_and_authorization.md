# Authentication and authorization

Status: implemented; standard and explicitly selected local Dex profiles confirmed.

## Overview

This document defines how payment requests are authenticated and authorized,
including JWT validation, the authentication opt-out, and operational endpoint protection.

Payment authentication and payer authorization are enabled by default. Operational
endpoints require the separate static API key regardless of payment-auth settings.

## Decisions

- Use JWT-based authentication with a configuration switch, `AUTH_ENABLED`. The scope and responsibility assumptions are recorded in [assumptions](assumptions.md#authentication-and-authorization); deployments must be able to disable these checks explicitly.
- Default `AUTH_ENABLED` to true; disabling authentication requires an explicit configuration change (confirmed).
- When authentication is disabled, payment requests require no token and skip token validation and payer authorization.
- `/health/live`, `/health/ready`, and `/metrics` use separate static API-key protection regardless of `AUTH_ENABLED` (confirmed). They must not be exposed to the internet; see [observability](observability.md#health-endpoints-and-access-protection).
- When enabled, accept a bearer JWT in the `Authorization` header. Verify its signature using public keys fetched from a configured JWKS URL.
- Require an expiration claim and reject expired tokens. Supply issuer and audience through required configuration values when authentication is enabled, and validate both claims (confirmed).
- The default `AUTH_TOKEN_PROFILE=standard` accepts only ES256 and the `payer_firm_uuid` claim (confirmed). The explicitly selected `dex` profile accepts only RS256 and the `federated_claims.user_id` claim, with `federated_claims.connector_id` required to be `local`. Never select a profile, algorithm, or key URL from a token.
- Require the selected profile's payer claim to be a string UUID matching the JSON request's `payer_firm_uuid`, comparing both as parsed UUIDs. A standard payer claim cannot substitute for missing or invalid Dex identity.
- Return 401 for a missing or invalid token, including a missing or malformed payer claim, and 403 for a valid token whose payer UUID does not match the request.
- If a token cannot be verified because keys are unavailable, deny access; never fall back to disabled authentication.
- Keep JWT verification and payer authorization in `auth/`, called through API dependencies before payment processing. Require HTTPS for the configured key URL and service ingress in deployed environments.

## Implementation decisions

- Fetch public keys from the configured JWKS URL for each authenticated request, with a bounded timeout. Do not cache keys initially (confirmed): caching adds complexity that is not justified by the expected traffic. Ensure the selected library does not enable an implicit key cache.
- Configure the public-key fetch timeout through `AUTH_JWKS_TIMEOUT_SECONDS`, defaulting to 30 seconds (confirmed).
- Use PyJWT with its cryptography extra rather than implementing cryptography. Disable both `cache_jwk_set` and `cache_keys`; verification uses only the configured JWKS URL.
- Require nonempty `AUTH_ISSUER`, `AUTH_AUDIENCE`, and `AUTH_JWKS_URL` at startup when authentication is enabled. Validate a positive finite fetch timeout. Disabled authentication does not require these values.
- Require HTTPS for the JWKS URL by default. `AUTH_ALLOW_HTTP=true` explicitly permits HTTP for local development and tests; deployed service ingress must use HTTPS through deployment infrastructure. Reject credentials and fragments in JWKS URLs.
- Authenticate through a synchronous FastAPI dependency before parsing the body. Validate the payment request, then authorize the payer before collecting transaction metrics or calling the payment service. Invalid tokens return 401 even when the request body is invalid; authenticated invalid bodies return the existing 422 errors before payer comparison.
- Authentication and authorization errors use the existing correlated `request_id`/`detail` response. Authentication failures include `WWW-Authenticate: Bearer`. Key-fetch or token errors never expose tokens, credentials, or network details.
- Load authentication configuration through a request dependency so the explicit environment opt-out applies to each request, including existing payment contract fixtures. Other application settings retain their existing startup lifetime.

## Local Dex

The local Compose setup explicitly selects `AUTH_TOKEN_PROFILE=dex` and
`AUTH_ALLOW_HTTP=true`. This is an agreed extension to the standard design:
Dex's local signer uses RS256 and does not emit an arbitrary `payer_firm_uuid`
claim. Its verified `federated_claims.user_id` represents the authorized firm for
the configured local connector. There is no automatic fallback between profiles.

Compose runs Dex with memory storage and local password users defined in
`local/dex.yaml`. The local users' IDs are firm UUIDs, not independent person IDs;
this fixture identity convention is for local development and tests. Each user
is authorized for exactly one payer. The password grant and published credentials
are local only; the service does not implement login or user management.

Dex's issuer is `http://localhost:5556/dex`; tokens are obtained from its
`/token` endpoint with scopes `openid federated:id`. Use the returned `id_token`
as the bearer JWT, not the opaque OAuth access token. The app fetches public
keys over Compose networking at `http://dex:5556/dex/keys`; issuer validation
still compares against the public issuer. Dex is exposed only on loopback.

`make up` and `make test` wait for Dex discovery readiness. The standard profile
is separately tested with generated ES256 keys. Functional authentication tests must
use real Dex-issued tokens and PostgreSQL; existing payment contracts explicitly
disable payment authentication.

## Basis

Authentication and authorization originate from a [design assumption](assumptions.md#authentication-and-authorization),
not from the task's requirements. The rules above and configurable opt-out are
design decisions agreed during design review.
