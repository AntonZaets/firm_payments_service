from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from firm_payments_service.api.schemas import (
    BulkPayment,
    Error,
    InvalidRequest,
    Payment,
    validate_request,
)
from firm_payments_service.config import Settings
from firm_payments_service.payments import service


class SerializationFailure(Exception):
    sqlstate = "40001"


def _serialization_error() -> DBAPIError:
    return DBAPIError(None, None, SerializationFailure())


def test_payment_validation_converts_dollars_to_cents() -> None:
    payer, payee = str(uuid4()), str(uuid4())
    request = validate_request(
        {
            "payer_firm_uuid": payer.upper(),
            "payments": [
                {
                    "payee_firm_uuid": payee.upper(),
                    "amount": "5800.5",
                    "description": "invoice",
                }
            ],
        },
        Settings(),
    )

    assert request.payer_firm_uuid == payer
    assert request.payments == [Payment(payee, 580_050, "invoice")]


def test_payment_validation_reports_all_schema_errors() -> None:
    payer = str(uuid4())

    with pytest.raises(InvalidRequest) as error:
        validate_request(
            {
                "payer_firm_uuid": payer,
                "payments": [
                    {
                        "payee_firm_uuid": payer,
                        "amount": "0.001",
                        "description": 3,
                    }
                ],
            },
            Settings(),
        )

    assert [item.code for item in error.value.errors] == [
        "INVALID_AMOUNT",
        "INVALID_FIELD",
        "SELF_PAYMENT",
    ]


def test_transfer_retries_serialization_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERIALIZATION_ATTEMPTS", "2")
    monkeypatch.setenv("SERIALIZATION_RETRY_DELAY_MS", "1")
    request = BulkPayment(str(uuid4()), [Payment(str(uuid4()), 1, "invoice")])
    calls = 0
    delays: list[float] = []

    def fail_once(
        sent_request: BulkPayment,
        raw_request: dict[str, object],
        request_id: str,
        settings: Settings,
    ) -> None:
        nonlocal calls
        assert delays == ([] if calls == 0 else [0.001])
        calls += 1
        assert sent_request == request
        assert raw_request == {"request": "body"}
        assert request_id == "request-id"
        assert settings.serialization_attempts == 2
        if calls == 1:
            raise _serialization_error()

    monkeypatch.setattr(service, "_attempt", fail_once)
    monkeypatch.setattr(service.time, "sleep", delays.append)

    service.transfer(
        request,
        {"request": "body"},
        "request-id",
        Settings(),
    )

    assert calls == 2
    assert delays == [0.001]


def test_transfer_reports_exhausted_serialization_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERIALIZATION_ATTEMPTS", "1")
    sleep = Mock()
    monkeypatch.setattr(service.time, "sleep", sleep)

    def fail(
        request: BulkPayment,
        raw_request: dict[str, object],
        request_id: str,
        settings: Settings,
    ) -> None:
        raise _serialization_error()

    monkeypatch.setattr(service, "_attempt", fail)

    with pytest.raises(service.SerializationExhausted):
        service.transfer(
            BulkPayment(str(uuid4()), [Payment(str(uuid4()), 1, "invoice")]),
            {},
            "request-id",
            Settings(),
        )

    sleep.assert_not_called()


@pytest.mark.parametrize("duplicate_index", [0, 1])
def test_firm_resolution_rejects_mixed_case_duplicates(
    monkeypatch: pytest.MonkeyPatch, duplicate_index: int
) -> None:
    payer = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    payee = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    rows = [SimpleNamespace(id=1, uuid=payer), SimpleNamespace(id=2, uuid=payee)]
    rows.append(SimpleNamespace(id=3, uuid=rows[duplicate_index].uuid.upper()))
    find_firms = Mock(return_value=rows)
    monkeypatch.setattr(service.repository, "find_firms", find_firms)

    with Session() as session:
        monkeypatch.setattr(
            service, "make_session", Mock(return_value=nullcontext(session))
        )
        with pytest.raises(InvalidRequest) as error:
            service.transfer(
                BulkPayment(payer, [Payment(payee, 1, "invoice")]),
                {},
                "request-id",
                Settings(),
            )

    assert error.value.errors == [
        Error("UNKNOWN_FIRM", "A firm UUID does not resolve to exactly one firm.")
    ]
    find_firms.assert_called_once_with(session, {payer, payee})


@pytest.mark.parametrize("sqlstate", ["40P01", "55P03", "57014", None])
def test_transfer_does_not_retry_other_database_errors(
    monkeypatch: pytest.MonkeyPatch, sqlstate: str | None
) -> None:
    monkeypatch.setenv("SERIALIZATION_ATTEMPTS", "3")
    original = Exception("database failure")
    if sqlstate is not None:
        monkeypatch.setattr(original, "sqlstate", sqlstate, raising=False)
    failure = DBAPIError(None, None, original)
    attempt = Mock(side_effect=failure)
    sleep = Mock()
    monkeypatch.setattr(service, "_attempt", attempt)
    monkeypatch.setattr(service.time, "sleep", sleep)

    with pytest.raises(DBAPIError) as error:
        service.transfer(
            BulkPayment(str(uuid4()), [Payment(str(uuid4()), 1, "invoice")]),
            {},
            "request-id",
            Settings(),
        )

    assert error.value is failure
    attempt.assert_called_once()
    sleep.assert_not_called()
