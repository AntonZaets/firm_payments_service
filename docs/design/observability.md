# Observability

Status: logging, metrics, and health endpoints confirmed; platform conventions and deployment targets remain open.

## Overview

This document defines logging, request correlation, metrics, and health checks
used to operate the service, along with endpoint protection and infrastructure responsibilities.

## Logging and request correlation

- Emit structured JSON logs to stdout using python-json-logger; let deployment infrastructure collect them.
- Include a service-generated request ID, route, status, duration, and outcome. Return the request ID to the client for troubleshooting.
- Return the generated ID in `X-Request-ID` on every response and as `request_id` in operational error bodies. Ignore caller-supplied request IDs. Log route templates rather than raw URLs or query strings; record duration in seconds and outcome as `success` or `failure`.
- Log unexpected failures with stack traces; emit a successful-payment event only after commit.
- Include the request ID in failure logs and error responses (confirmed). Preserve it across serialization retries so all attempts correlate with the same request.
- Exclude credentials, request bodies, payment descriptions, and balances from logs. Stored payment rows remain the financial record.

Transactional audit storage and permissions are defined in [data model](data-model.md#audit-table).

## Metrics

- Expose prometheus-client metrics on an internal-only endpoint (confirmed).
- Measure request count and latency by route and status, payment-batch outcomes, and database transaction failures (confirmed).
- Keep metric labels bounded; never label by firm UUID, request ID, or payment description (confirmed).

## Health endpoints and access protection

- Provide separate liveness and readiness endpoints; readiness checks database connectivity, while liveness does not depend on the database (confirmed).
- Use `/health/live`, `/health/ready`, and `/metrics`, protected by a static API key rather than JWT authentication (confirmed). Store the key in deployment secrets; probes and metrics scrapers must supply it. This protection remains enabled even when payment JWT authentication is disabled.
- Configure the key through required, nonempty `OPERATIONAL_API_KEY`; reject missing or empty configuration. Missing or incorrect keys return HTTP 401. Compose supplies a local-development default only.
- Supply the static key in the `X-API-Key` header (confirmed). Never include it in URLs or logs.
- These endpoints must not be exposed to the internet (confirmed). Restrict access through private networking and ingress rules; the API key is additional protection, not a substitute for network restrictions.

## Infrastructure responsibilities

- Alert rules, thresholds, routing, and notifications are outside the service scope and belong to the infrastructure monitoring setup. The service exposes metrics and health endpoints for that setup to consume (confirmed).
- Under the [execution model](architecture.md#execution-model), each container exposes its own process metrics for infrastructure to scrape; no Prometheus multiprocess setup is needed.

Platform logging conventions, retention, access controls, additional audit
requirements, monitoring infrastructure, and operational targets must be
validated with their owners; see [assumptions](assumptions.md).

## Requirements

Supports investigation and operation of FR-05 and NFR-01–NFR-02. Endpoint
access protection is a design decision, not a requirement from the task.
