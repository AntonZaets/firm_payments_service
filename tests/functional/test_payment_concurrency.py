from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from httpx2 import Response
from sqlalchemy import Engine, text

from .conftest import ENDPOINT, ClientFactory, SeedFirm
from .factories import Firm, Payload, PaymentFactory, request_for

pytestmark = pytest.mark.just_contract


def concurrent_requests(
    client_factory: ClientFactory, payloads: list[Payload]
) -> list[Response]:
    clients = [client_factory() for _ in payloads]
    barrier = Barrier(len(payloads))

    def send(index: int) -> Response:
        barrier.wait(timeout=10)
        return clients[index].post(ENDPOINT, json=payloads[index])

    with ThreadPoolExecutor(max_workers=len(payloads)) as executor:
        return list(executor.map(send, range(len(payloads))))


def assert_committed(
    engine: Engine,
    firms: list[Firm],
    balances: list[int],
    payloads: list[Payload],
    responses: list[Response],
) -> None:
    with engine.connect() as connection:
        actual = dict(
            connection.execute(text("SELECT id, balance_cents FROM firms"))
            .tuples()
            .all()
        )
        assert actual == dict(zip([firm.id for firm in firms], balances, strict=True))
        assert sum(actual.values()) == sum(firm.balance_cents for firm in firms)
        ids = {firm.uuid: firm.id for firm in firms}
        expected = [
            (
                ids[payload["payer_firm_uuid"]],
                ids[payload["payments"][0]["payee_firm_uuid"]],
                100,
                payload["payments"][0]["description"],
            )
            for payload in payloads
        ]
        rows = (
            connection.execute(
                text(
                    "SELECT payer_firm_id, payee_firm_id, amount_cents, "
                    "description FROM payments"
                )
            )
            .tuples()
            .all()
        )
        assert sorted(rows) == sorted(expected)
        audits = (
            connection.execute(
                text("SELECT request_id, raw_request FROM firm_payments_audit")
            )
            .tuples()
            .all()
        )
        assert len(audits) == len(payloads)
        assert {str(row[0]) for row in audits} == {
            response.json()["request_id"] for response in responses
        }
        assert all(row[1] in payloads for row in audits)


def test_concurrent_overspending(
    client_factory: ClientFactory,
    db_engine: Engine,
    firm_factory: SeedFirm,
) -> None:
    payer = firm_factory(balance_cents=150)
    recipients = [firm_factory(balance_cents=0) for _ in range(2)]
    payloads = [
        request_for(payer, PaymentFactory.build(payee_firm_uuid=firm.uuid))
        for firm in recipients
    ]
    responses = concurrent_requests(client_factory, payloads)
    assert sum(response.status_code == 201 for response in responses) == 1
    winner = next(
        index for index, response in enumerate(responses) if response.status_code == 201
    )
    loser = responses[1 - winner]
    assert loser.status_code in {422, 503}, loser.text
    if loser.status_code == 422:
        assert "INSUFFICIENT_FUNDS" in {
            error["code"] for error in loser.json()["errors"]
        }
    else:
        assert int(loser.headers["Retry-After"]) >= 1
    assert_committed(
        db_engine,
        [payer, *recipients],
        [50, 100 if winner == 0 else 0, 100 if winner == 1 else 0],
        [payloads[winner]],
        [responses[winner]],
    )


@pytest.mark.parametrize(
    "opposite_roles", [False, True], ids=["shared-recipient", "payer-also-receives"]
)
def test_concurrent_shared_firms(
    client_factory: ClientFactory,
    db_engine: Engine,
    firm_factory: SeedFirm,
    opposite_roles: bool,
) -> None:
    firms = [firm_factory() for _ in range(3)]
    first, second, third = firms
    transfers = (
        [(first, second), (second, third)]
        if opposite_roles
        else [(first, third), (second, third)]
    )
    payloads = [
        request_for(payer, PaymentFactory.build(payee_firm_uuid=payee.uuid))
        for payer, payee in transfers
    ]
    responses = concurrent_requests(client_factory, payloads)
    assert [response.status_code for response in responses] == [201, 201]
    balances = (
        [99_900, 100_000, 100_100] if opposite_roles else [99_900, 99_900, 100_200]
    )
    assert_committed(db_engine, firms, balances, payloads, responses)
