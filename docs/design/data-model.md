# Data model

Status: platform schema ownership, transactional audit, audit columns, and append-only enforcement confirmed; remaining details proposed.

## Overview

This document defines how the service uses platform firm and payment data,
represents money, and defines the service-owned audit schema and permissions.

## Storage decisions

- Integrate with the existing platform `firms` and `payments` tables; do not create duplicate balance storage.
- The platform owns these tables. No schema changes are allowed; read and write their data only as required by the payment requirements (confirmed).
- Preserve one payment row per input entry, including repeated recipients and their separate descriptions.
- Resolve public UUIDs to internal IDs before inserting payments.
- Store and calculate money as integer cents. Validate the dollar-string format before exact conversion; never use floating point.
- The requirements do not specify existing database constraints or establish permission to alter platform tables. Database-enforced primary keys, unique firm UUIDs, foreign keys, positive payment amounts, and appropriate balance constraints are best practice, but the service must not assume they exist or introduce platform schema changes without platform approval (confirmed).
- Validate monetary values against the actual database integer ranges. The platform's negative-balance policy is unknown; service behavior for payer and recipient balances is defined in [architecture](architecture.md#payment-transaction).
- Transaction-level validation, firm resolution, and balance updates are defined in [architecture](architecture.md#payment-transaction). Client submission and idempotency behavior are defined in [API](api.md#payment-endpoint).

## Audit table

Maintain an additional service-owned, append-only table for data updates
(confirmed). The table is named `firm_payments_audit` (confirmed), with these
confirmed columns:

| Column | PostgreSQL type | Purpose |
| --- | --- | --- |
| id | BIGINT identity, primary key | Identify the audit record. |
| created_at | TIMESTAMPTZ, not null | Record when the update occurred, using a database-generated timestamp. |
| request_id | UUID, not null | Correlate the update with the service-generated request ID. |
| raw_request | JSON, not null | Original parsed JSON request body, before schema normalization or conversion to cents. |

Audit insertion and rollback behavior are defined in the
[payment transaction](architecture.md#payment-transaction).

Never update or delete audit rows. Confirmed enforcement: give the runtime role
INSERT and SELECT permissions only on the audit table; use a separate migration
role for ownership and schema changes. Alembic manages only service-owned schema.
The audit body contains payment descriptions and amounts, so restrict access;
do not include authorization headers or credentials.

## Integration assumptions

See [platform constraints, indexes, and schema changes](assumptions.md#platform-constraints-indexes-and-schema-changes) for checks to complete during integration.

## Requirements

FR-02–FR-03, FR-06–FR-07, NFR-03–NFR-04.
