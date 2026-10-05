from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .assertions import assert_rejected
from .conftest import ENDPOINT, SeedFirm, Snapshot
from .factories import Firm, Payload

pytestmark = pytest.mark.usefixtures("existing_records")


@pytest.mark.parametrize("balance", [1433, 0, -1])
def test_insufficient_funds(
    client: TestClient,
    db_engine: Engine,
    transfer_case: tuple[list[Firm], Payload],
    database_snapshot: Snapshot,
    balance: int,
) -> None:
    firms, payload = transfer_case
    with db_engine.begin() as connection:
        connection.execute(
            text("UPDATE firms SET balance_cents=:balance WHERE id=:id"),
            {"balance": balance, "id": firms[0].id},
        )
    before = database_snapshot()
    assert_rejected(
        client.post(ENDPOINT, json=payload),
        before,
        database_snapshot(),
        "INSUFFICIENT_FUNDS",
    )


@pytest.mark.parametrize("field", ["payer", "payee"])
def test_unknown_firm(
    client: TestClient,
    transfer_case: tuple[list[Firm], Payload],
    database_snapshot: Snapshot,
    field: str,
) -> None:
    _, payload = transfer_case
    if field == "payer":
        payload["payer_firm_uuid"] = str(uuid4())
    else:
        payload["payments"][1]["payee_firm_uuid"] = str(uuid4())
    before = database_snapshot()
    assert_rejected(
        client.post(ENDPOINT, json=payload), before, database_snapshot(), "UNKNOWN_FIRM"
    )


@pytest.mark.parametrize("index", [0, 1])
def test_ambiguous_firm(
    client: TestClient,
    firm_factory: SeedFirm,
    transfer_case: tuple[list[Firm], Payload],
    database_snapshot: Snapshot,
    index: int,
) -> None:
    firms, payload = transfer_case
    firm_factory(uuid=firms[index].uuid)
    before = database_snapshot()
    assert_rejected(
        client.post(ENDPOINT, json=payload), before, database_snapshot(), None
    )


@pytest.mark.parametrize(
    "amount",
    ["0", "0.00", "-1", "1.001", " 1", "1 ", "1e2", "abc", "", "NaN", 1, 1.5, None],
)
def test_invalid_amount(
    client: TestClient,
    transfer_case: tuple[list[Firm], Payload],
    database_snapshot: Snapshot,
    amount: Any,
) -> None:
    _, payload = transfer_case
    payload["payments"][1]["amount"] = amount
    before = database_snapshot()
    # Wrong JSON types are schema errors; invalid strings are amount errors.
    code = "INVALID_AMOUNT" if isinstance(amount, str) else "INVALID_FIELD"
    assert_rejected(
        client.post(ENDPOINT, json=payload), before, database_snapshot(), code
    )


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("empty", "EMPTY_PAYMENTS"),
        ("self", "SELF_PAYMENT"),
        ("self_upper", "SELF_PAYMENT"),
        ("payer_uuid", "INVALID_UUID"),
        ("payee_uuid", "INVALID_UUID"),
        ("batch_limit", "INVALID_FIELD"),
        ("description_limit", "INVALID_FIELD"),
    ],
)
def test_validation_rules(
    client: TestClient,
    transfer_case: tuple[list[Firm], Payload],
    database_snapshot: Snapshot,
    case: str,
    code: str,
) -> None:
    _, payload = transfer_case
    payment = payload["payments"][0]
    if case == "empty":
        payload["payments"] = []
    elif case.startswith("self"):
        payment["payee_firm_uuid"] = payload["payer_firm_uuid"]
        if case == "self_upper":
            payment["payee_firm_uuid"] = payment["payee_firm_uuid"].upper()
    elif case == "payer_uuid":
        payload["payer_firm_uuid"] = "invalid"
    elif case == "payee_uuid":
        payment["payee_firm_uuid"] = "invalid"
    elif case == "batch_limit":
        payload["payments"] = [payment.copy() for _ in range(1001)]
    else:
        payment["description"] = "x" * 1001
    before = database_snapshot()
    assert_rejected(
        client.post(ENDPOINT, json=payload), before, database_snapshot(), code
    )


@pytest.mark.parametrize(
    "field", ["payer_firm_uuid", "payments", "payee_firm_uuid", "amount", "description"]
)
@pytest.mark.parametrize("mutation", ["missing", "wrong_type"])
def test_required_fields(
    client: TestClient,
    transfer_case: tuple[list[Firm], Payload],
    database_snapshot: Snapshot,
    field: str,
    mutation: str,
) -> None:
    _, payload = transfer_case
    target = (
        payload if field in {"payer_firm_uuid", "payments"} else payload["payments"][0]
    )
    if mutation == "missing":
        del target[field]
    else:
        target[field] = {} if field == "payments" else []
    before = database_snapshot()
    assert_rejected(
        client.post(ENDPOINT, json=payload),
        before,
        database_snapshot(),
        "INVALID_FIELD",
    )


@pytest.mark.parametrize(
    "body", [[], "body", 42, {"payer_firm_uuid": "bad", "payments": [42]}]
)
def test_wrong_body_or_entry_type(
    client: TestClient,
    database_snapshot: Snapshot,
    body: Any,
) -> None:
    before = database_snapshot()
    assert_rejected(
        client.post(ENDPOINT, json=body), before, database_snapshot(), "INVALID_FIELD"
    )


def test_malformed_json(client: TestClient, database_snapshot: Snapshot) -> None:
    before = database_snapshot()
    response = client.post(
        ENDPOINT, content="{", headers={"Content-Type": "application/json"}
    )
    assert_rejected(response, before, database_snapshot(), "INVALID_JSON")


@pytest.mark.parametrize("case", ["payment", "total", "recipient"])
def test_integer_overflow(
    client: TestClient,
    db_engine: Engine,
    transfer_case: tuple[list[Firm], Payload],
    database_snapshot: Snapshot,
    case: str,
) -> None:
    firms, payload = transfer_case
    if case == "payment":
        payload["payments"][0]["amount"] = "21474836.48"
    elif case == "total":
        for payment in payload["payments"]:
            payment["amount"] = "10737418.24"
    else:
        with db_engine.begin() as connection:
            connection.execute(
                text("UPDATE firms SET balance_cents=2147483647 WHERE id=:id"),
                {"id": firms[1].id},
            )
    before = database_snapshot()
    assert_rejected(
        client.post(ENDPOINT, json=payload), before, database_snapshot(), None
    )


def test_multiple_errors(
    client: TestClient,
    transfer_case: tuple[list[Firm], Payload],
    database_snapshot: Snapshot,
) -> None:
    _, payload = transfer_case
    payload["payments"][0]["amount"] = "0"
    payload["payments"][1]["payee_firm_uuid"] = "bad"
    before = database_snapshot()
    response = client.post(ENDPOINT, json=payload)
    assert_rejected(response, before, database_snapshot(), None)
    assert {"INVALID_AMOUNT", "INVALID_UUID"} <= {
        error["code"] for error in response.json()["errors"]
    }
