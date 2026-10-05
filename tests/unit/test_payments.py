from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from firm_payments_service.api.schemas import (
    BulkPayment,
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


def _noop_sleep(seconds: float) -> None:
    pass


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

    def fail_once(
        sent_request: BulkPayment,
        raw_request: dict[str, object],
        request_id: str,
        settings: Settings,
    ) -> None:
        nonlocal calls
        calls += 1
        assert sent_request == request
        assert raw_request == {"request": "body"}
        assert request_id == "request-id"
        assert settings.serialization_attempts == 2
        if calls == 1:
            raise _serialization_error()

    monkeypatch.setattr(service, "_attempt", fail_once)
    monkeypatch.setattr(service.time, "sleep", _noop_sleep)

    service.transfer(
        request,
        {"request": "body"},
        "request-id",
        Settings(),
    )

    assert calls == 2


def test_transfer_reports_exhausted_serialization_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERIALIZATION_ATTEMPTS", "1")

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
