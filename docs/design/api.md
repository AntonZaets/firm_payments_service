# API

Status: endpoint, validation limits, and response conventions confirmed.

## Overview

This document defines the bulk-payment endpoint, client-facing validation,
request schema and headers, response formats, and HTTP status mapping.

## Payment endpoint

- Expose bulk payment submission at `POST /api/v1/payments/bulk`.
- Return HTTP 201 with `{"request_id": "..."}` only after the payment transaction commits.
- Generate a request ID in the service and return it for troubleshooting; it is for correlation, not deduplication.
- Client-request idempotency is out of scope. Repeated HTTP submissions are separate transfers; no idempotency key or replay-protection storage is introduced.
- Payment requests require bearer authentication and payer authorization unless `AUTH_ENABLED=false`. Operational endpoints are defined in [observability](observability.md) and remain API-key protected.

## Request headers

| Header | Value | Required |
| --- | --- | --- |
| `Content-Type` | `application/json` | Yes. |
| `Authorization` | `Bearer <JWT>` | When `AUTH_ENABLED=true` (the default). |

JWT validation and payer authorization follow
[authentication and authorization](authentication_and_authorization.md).
Missing or invalid tokens return HTTP 401 with `WWW-Authenticate: Bearer`;
a valid token for a different payer returns HTTP 403. Both responses contain
`request_id` and a generic `detail` and leave the database unchanged.

## Request schema

All fields below are required. The body is a JSON object; each entry in
`payments` is a JSON object representing one payment.

| Field | JSON type | Meaning and constraints |
| --- | --- | --- |
| `payer_firm_uuid` | String | Public UUID of the paying firm; must be a valid UUID. |
| `payments` | Array of objects | Nonempty payment list; default maximum 1,000 entries. |
| `payments[].payee_firm_uuid` | String | Public UUID of the receiving firm; must be a valid UUID different from the payer UUID. Repeated recipients are allowed. |
| `payments[].amount` | String | Strictly positive US-dollar amount with zero, one, or two decimal places, such as `"300"`, `"5800.5"`, or `"1200.75"`. JSON numbers are not accepted. |
| `payments[].description` | String | Payment description; default maximum 1,000 characters, subject to stricter platform column limits. |

Example body:

```json
{
  "payer_firm_uuid": "3f1c9a2e-7b4d-4c1e-9a55-2d8e6f0b7c41",
  "payments": [
    {
      "payee_firm_uuid": "8b2e4c71-0d3a-4f6e-b1c9-5a7d2e9f4c10",
      "amount": "1200.75",
      "description": "Bookkeeping cleanup, 3 clients"
    }
  ]
}
```

## Validation

- Reject empty payment lists and self-payments with HTTP 422. A self-payment is an entry whose payee UUID equals the payer UUID; these checks help catch client bugs.
- Configure batch-size and description-length limits, defaulting to 1,000 payments per batch and 1,000 characters per description. Respect any stricter existing platform column limits. Reject exceeded limits with HTTP 422 and `INVALID_FIELD` before database writes.
- Validate the dollar-string format before exact conversion to integer cents; never use floating point. See [data model](data-model.md) for monetary representation and supported ranges.
- Unknown payer or payee UUIDs return HTTP 422 with `UNKNOWN_FIRM`; insufficient funds returns HTTP 422 with `INSUFFICIENT_FUNDS` as required by FR-04.
- A rejected request persists no balance, payment, or audit changes. See [payment transaction](architecture.md#payment-transaction) for transaction-level checks.

## Validation error response

Confirmed response shape:

```json
{
  "request_id": "f31f8a27-dc53-41de-82bc-0a94104aaec0",
  "errors": [
    {
      "code": "INVALID_AMOUNT",
      "details": "payments[0].amount has invalid value \"0\": expected a positive dollar string with at most two decimal places."
    }
  ]
}
```

Each error has a stable string code from a defined error set and human-readable
details identifying the field and invalid value (confirmed). Clients use codes
for programmatic handling; wording of details may change. Never include tokens
or credentials in details. Return multiple errors when available without
continuing to database writes.

Confirmed error set:

| Code | Meaning |
| --- | --- |
| INVALID_JSON | Body is not valid JSON. |
| INVALID_FIELD | Missing field, incorrect type, or another schema violation. |
| INVALID_UUID | A firm identifier is not a valid UUID. |
| INVALID_AMOUNT | Amount format, positivity, or supported integer range is invalid. |
| EMPTY_PAYMENTS | Payment list is empty. |
| SELF_PAYMENT | Payee UUID matches payer UUID. |
| UNKNOWN_FIRM | Payer or payee UUID does not resolve to a platform firm. |
| INSUFFICIENT_FUNDS | Payer balance is below the batch total. |

## Database failure responses

- When serialization retries are exhausted, return HTTP 503 with the request ID and a `Retry-After` header expressed in seconds. Configure `Retry-After`, defaulting to 1 second.
- Other database failures return HTTP 500 with the request ID and a generic error message. Never expose internal database details to clients.
- The retry policy is defined in [architecture](architecture.md#concurrency-and-failures); failures are logged with the same request ID according to [observability](observability.md).

## Requirements

FR-01–FR-06, NFR-01–NFR-04. Authentication and authorization follow the confirmed
service design.
