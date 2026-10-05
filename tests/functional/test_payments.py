import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from .assertions import assert_success
from .conftest import ENDPOINT, SeedFirm
from .factories import Firm, Payload, PaymentFactory, request_for


def test_pdf_example(
    client: TestClient, db_engine: Engine, pdf_example: tuple[list[Firm], Payload]
) -> None:
    firms, payload = pdf_example
    assert_success(
        response=client.post(ENDPOINT, json=payload),
        engine=db_engine,
        firms=firms,
        payload=payload,
        balances=[3_674_875, 170_075, 1_405_050],
        cents=[625_000, 580_050, 120_075],
    )


def test_multiple_recipients(
    client: TestClient, db_engine: Engine, transfer_case: tuple[list[Firm], Payload]
) -> None:
    firms, payload = transfer_case
    assert_success(
        response=client.post(ENDPOINT, json=payload),
        engine=db_engine,
        firms=firms,
        payload=payload,
        balances=[98_566, 101_234, 100_200, 100_000],
        cents=[1234, 200],
    )


@pytest.mark.parametrize(
    ("amount", "cents"),
    [("300", 30_000), ("5800.5", 580_050), ("1200.75", 120_075), ("0.01", 1)],
)
def test_single_payment_exact_conversion(
    client: TestClient,
    db_engine: Engine,
    firm_factory: SeedFirm,
    amount: str,
    cents: int,
) -> None:
    payer = firm_factory(balance_cents=1_000_000)
    recipient = firm_factory()
    payload = request_for(
        payer, PaymentFactory.build(payee_firm_uuid=recipient.uuid, amount=amount)
    )
    assert_success(
        response=client.post(ENDPOINT, json=payload),
        engine=db_engine,
        firms=[payer, recipient],
        payload=payload,
        balances=[1_000_000 - cents, 100_000 + cents],
        cents=[cents],
    )


def test_repeated_recipient(
    client: TestClient, db_engine: Engine, firm_factory: SeedFirm
) -> None:
    payer, recipient = firm_factory(), firm_factory()
    payload = request_for(
        payer,
        *[
            PaymentFactory.build(
                payee_firm_uuid=recipient.uuid, amount=amount, description=description
            )
            for amount, description in [("1.00", "first"), ("2.50", "second")]
        ],
    )
    assert_success(
        response=client.post(ENDPOINT, json=payload),
        engine=db_engine,
        firms=[payer, recipient],
        payload=payload,
        balances=[99_650, 100_350],
        cents=[100, 250],
    )


@pytest.mark.parametrize("recipient_balance", [100_000, -50, -200])
def test_exact_funds_and_negative_recipient(
    client: TestClient,
    db_engine: Engine,
    firm_factory: SeedFirm,
    recipient_balance: int,
) -> None:
    payer = firm_factory(balance_cents=100)
    recipient = firm_factory(balance_cents=recipient_balance)
    payload = request_for(payer, PaymentFactory.build(payee_firm_uuid=recipient.uuid))
    assert_success(
        response=client.post(ENDPOINT, json=payload),
        engine=db_engine,
        firms=[payer, recipient],
        payload=payload,
        balances=[0, recipient_balance + 100],
        cents=[100],
    )


def test_repeated_submission(
    client: TestClient, db_engine: Engine, transfer_case: tuple[list[Firm], Payload]
) -> None:
    firms, payload = transfer_case
    first = client.post(ENDPOINT, json=payload)
    assert first.status_code == 201, first.text
    second = client.post(ENDPOINT, json=payload)
    assert_success(
        response=second,
        engine=db_engine,
        firms=firms,
        payload=payload,
        balances=[97_132, 102_468, 100_400, 100_000],
        cents=[1234, 200],
        submissions=2,
    )
    assert first.json()["request_id"] != second.json()["request_id"]


@pytest.mark.parametrize(("count", "length"), [(1000, 1), (1, 1000)])
def test_limits_accepted(
    client: TestClient,
    db_engine: Engine,
    firm_factory: SeedFirm,
    count: int,
    length: int,
) -> None:
    payer, recipient = firm_factory(), firm_factory()
    payload = request_for(
        payer,
        *[
            PaymentFactory.build(
                payee_firm_uuid=recipient.uuid, amount="0.01", description="x" * length
            )
            for _ in range(count)
        ],
    )
    assert_success(
        response=client.post(ENDPOINT, json=payload),
        engine=db_engine,
        firms=[payer, recipient],
        payload=payload,
        balances=[100_000 - count, 100_000 + count],
        cents=[1] * count,
    )
