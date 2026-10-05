# Design assumptions

Status: provisional; validate with the platform and deployment owners during integration.

## Overview

This document records working assumptions for capacity, platform integration,
and deployment, identifying what must be validated before implementation or deployment.

## Firm population and payment volume

Source: user-supplied capacity-planning assumptions; these are estimates, not verified market statistics or measured platform traffic.

- Assume approximately 100,000 accounting firms in the USA, including individual practitioners as potential service users.
- Assume each active paying firm submits a few bulk payment requests per day (single digits).
- During tax season, assume hundreds of individual payments per bulk request; during ordinary months, assume tens of individual payments per bulk request.
- Daily request volume is the number of active paying firms multiplied by their daily bulk requests. Daily individual-payment volume also depends on the seasonal batch size; do not assume all 100,000 firms submit payments every day.
- The service is not expected to handle high traffic by nature; validate this assumption against deadline-day demand and actual batch sizes.
- For deadline-day planning, assume approximately 25% of the 100,000 firms submit payments on the last day: `100,000 × 0.25 = 25,000` participating firms. Use an eight-hour submission window: `8 × 60 × 60 = 28,800` seconds.
- With one bulk request per participating firm in that window, the average is `25,000 / 28,800 ≈ 0.87` requests per second across the service, roughly one request per second. If each firm submits several requests, multiply this rate by its average number of requests; individual payment records within a batch do not count as separate HTTP requests.
- Assume no more 10 requests per second during peak hour (x8 times more than computed in average) to have large supply for the future, so each request should be handled in 100ms or at worst in hundreds of milliseconds
- Use a provisional bulk-payment response-time goal of a few hundred milliseconds, ideally less than 100 ms, including authentication and transaction commit. Validate it under representative batch sizes, concurrency, JWKS fetch latency, and serialization retries before treating it as an operational target.
- Validate active-firm counts, daily request volumes, batch sizes, and peak concurrency against platform traffic before choosing deployment capacity.

## Authentication and authorization

- The initial task did not explicitly specify authentication or authorization mechanisms. NFR-05 requires unauthorized access to be denied; assume both are necessary for payment requests.
- Authentication could be handled by deployment infrastructure or an API gateway. Authorization remains a service responsibility: the service must verify that the authenticated caller is permitted to pay from the requested payer firm, rather than treating authentication alone as permission to transfer funds.
- The current design performs JWT verification and payer authorization in the service. Infrastructure-level authentication would require a trusted caller identity to reach the service and would not replace payer authorization. See [authentication and authorization](authentication_and_authorization.md) for the current rules and the explicit `AUTH_ENABLED` opt-out, which disables both checks.

## Platform constraints, indexes, and schema changes

- Assume no additional permission to change platform tables. Any future constraint or index changes require platform approval; migrations remain limited to service-owned schema.
- Treat existing constraints and indexes as unknown. Correctness relies on transaction-level validation rather than assumed database constraints.
- During integration, inspect the actual schema, integer ranges, constraints, and indexes. Confirm lookup performance and any permitted future schema changes with the platform owner.

## Other balance writers

- Assume they apply updates in ascending internal firm-ID order when modifying multiple firms. This reduces deadlock risk; it is not a correctness guarantee. Confirm whether all other platform balance writers use compatible transactional updates and lock ordering.

## Platform logging and audit conventions

- Assume no additional platform log-field or correlation-ID convention has been supplied. Use the service-generated request ID and the structured fields already defined in [observability](observability.md#logging-and-request-correlation).
- Assume deployment infrastructure collects stdout logs and owns retention and access policies. Do not invent a retention period in the service.
- Use the confirmed [transactional audit table](data-model.md#audit-table) as the service's audit record pending review of any additional platform audit requirements.
- Confirm required fields, correlation conventions, retention, access controls, and audit requirements with the platform owner before deployment.

## Monitoring infrastructure and targets

- Assume deployment infrastructure can scrape each container's metrics and call health endpoints over private networking with the configured API key.
- Assume infrastructure owners define alert thresholds, routing, notifications, and operational targets. The response-time goal above is a user-supplied planning assumption, not a target inferred from the requirements; no availability target is inferred.
- Confirm scraper and probe configuration, private access, and operational targets with the deployment owner before deployment.
