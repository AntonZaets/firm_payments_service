# Firm Payments Service Requirements

## Scope and source

The service transfers money between firms' platform balances through bulk
payment requests. Language choices, library preferences, submission instructions,
AI logs, README requirements, and other instructions to the task assignee are
outside this document's scope.

## Functional requirements

- **FR-01 — Bulk request:** Accept a JSON document identifying one paying firm
  through `payer_firm_uuid` and listing individual payments in `payments`.
- **FR-02 — Payment fields:** Each payment contains `payee_firm_uuid`, `amount`,
  and `description`. The amount is a strictly positive US-dollar string with
  zero, one, or two decimal places, such as `"300"`, `"5800.5"`, or `"1200.75"`.
- **FR-03 — Firm identification:** Resolve public firm UUIDs to internal firm
  IDs for balance updates and stored payment records.
- **FR-04 — Funds validation:** Compare the paying firm's available balance
  with the sum of all payments. A balance equal to the total is sufficient.
  If funds are insufficient, return HTTP **422** and leave all balances and
  payment records unchanged.
- **FR-05 — Successful transfer:** For an accepted request, store one payment
  record per entry, debit the paying firm by the total, credit each receiving
  firm by its payments, and return HTTP **201** after the changes commit.
- **FR-06 — Repeated recipients:** Support multiple entries for the same
  recipient within a request. Preserve their separate amounts and descriptions
  as individual payment records and credit the recipient by their sum.
- **FR-07 — Persistence:** Use the specified relational data model of the **platform**
  database with which service should be integrated (see the table descriptions below).

## Request format

A bulk payment request is a JSON document. Here is an example, with each
attribute explained in a comment (real requests carry no comments):

```jsonc
{
    // Identifies the firm that pays.
    "payer_firm_uuid": "3f1c9a2e-7b4d-4c1e-9a55-2d8e6f0b7c41",
    // Each entry is one payment to one firm.
    "payments": [
        {
            // Amount of the payment in US dollars, as a string, with at most
            // 2 optional decimal places. Always positive.
            "amount": "1200.75",
            // Identifies the firm that receives the payment.
            "payee_firm_uuid": "8b2e4c71-0d3a-4f6e-b1c9-5a7d2e9f4c10",
            // Description of the payment.
            "description": "Bookkeeping cleanup, 3 clients"
        },
        {
            "amount": "300",
            "payee_firm_uuid": "e5f18b3c-2a9d-4c07-8e6b-1d4a7f9c3b25",
            "description": "Referral fee, 2 clients"
        }
    ]
}
```

## The platform's database

The platform's database has two tables.

### firms

| Column | Type | Description |
| --- | --- | --- |
| id | INTEGER | Unique internal identifier of the firm. |
| name | TEXT | Name of the firm. |
| balance_cents | INTEGER | Current balance of the firm, in US cents. |
| uuid | TEXT | Public identifier of the firm, used in requests. |

### payments

| Column | Type | Description |
| --- | --- | --- |
| id | INTEGER | Unique identifier of the payment. |
| payer_firm_id | INTEGER | id of the firms row that pays. |
| payee_firm_id | INTEGER | id of the firms row that receives the payment. |
| amount_cents | INTEGER | Amount of the payment, in US cents. |
| description | TEXT | Description of the payment. |

## Non-functional requirements

- **NFR-01 — Atomicity:** Payment insertion and all balance changes must succeed
  or fail together. A failure must not leave a partially processed bulk request.
- **NFR-02 — Concurrent correctness:** Operate correctly across multiple
  load-balanced service instances sharing a relational database such as
  PostgreSQL or MySQL. Concurrent requests must not overspend a payer's balance
  or lose balance updates, including when a firm both pays and receives money.
- **NFR-03 — Monetary precision:** Convert dollar strings to integer cents
  exactly. Calculations and storage must avoid floating-point rounding errors.
- **NFR-04 — Balance integrity:** Each successful request must conserve the
  total balance across affected firms. Debits and credits must match the stored
  payment amounts, and funds validation must remain valid when changes commit.
