# Authentication and authorization

Status: deferred from the current payment implementation phase.

## Overview

This document defines how payment requests are authenticated and authorized,
including JWT validation, the authentication opt-out, and operational endpoint protection.

The current implementation intentionally skips payment authentication and
authorization. Operational endpoints continue to require the static API key. The
rules below describe the deferred payment-auth design to implement later.

## Decisions

- Use JWT-based authentication with a configuration switch, `AUTH_ENABLED`. The scope and responsibility assumptions are recorded in [assumptions](assumptions.md#authentication-and-authorization); deployments must be able to disable these checks explicitly.
- Default `AUTH_ENABLED` to true; disabling authentication requires an explicit configuration change (confirmed).
- When authentication is disabled, payment requests require no token and skip token validation and payer authorization.
- `/health/live`, `/health/ready`, and `/metrics` use separate static API-key protection regardless of `AUTH_ENABLED` (confirmed). They must not be exposed to the internet; see [observability](observability.md#health-endpoints-and-access-protection).
- When enabled, accept a bearer JWT in the `Authorization` header. Verify its signature using public keys fetched from a configured JWKS URL.
- Require an expiration claim and reject expired tokens. Supply issuer and audience through required configuration values when authentication is enabled, and validate both claims (confirmed).
- Allow only ES256 as the signing algorithm (confirmed); never accept an algorithm or key URL solely because the token specifies it.
- Require the token payload's `payer_firm_uuid` claim to match the JSON request's `payer_firm_uuid`, comparing both as parsed UUIDs.
- Return 401 for a missing or invalid token, including a missing or malformed payer claim, and 403 for a valid token whose payer UUID does not match the request.
- If a token cannot be verified because keys are unavailable, deny access; never fall back to disabled authentication.
- Keep JWT verification and payer authorization in `auth/`, called through API dependencies before payment processing. Require HTTPS for the configured key URL and service ingress in deployed environments.

## Implementation decisions

- Fetch public keys from the configured JWKS URL for each authenticated request, with a bounded timeout. Do not cache keys initially (confirmed): caching adds complexity that is not justified by the expected traffic. Ensure the selected library does not enable an implicit key cache.
- Configure the public-key fetch timeout through `AUTH_JWKS_TIMEOUT_SECONDS`, defaulting to 30 seconds (confirmed).
- Use an established JWT verification library rather than implementing cryptography.

## Basis

Authentication and authorization originate from a [design assumption](assumptions.md#authentication-and-authorization),
not from the task's requirements. The rules above and configurable opt-out are
design decisions agreed during design review.
