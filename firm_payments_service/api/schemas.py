import re
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from firm_payments_service.config import Settings

INTEGER_MAX = 2_147_483_647
AMOUNT = re.compile(r"^[0-9]+(?:\.[0-9]{1,2})?$")


@dataclass(frozen=True)
class Error:
    code: str
    details: str


@dataclass(frozen=True)
class Payment:
    payee_firm_uuid: str
    amount_cents: int
    description: str


@dataclass(frozen=True)
class BulkPayment:
    payer_firm_uuid: str
    payments: list[Payment]


class InvalidRequest(Exception):
    def __init__(self, errors: list[Error]) -> None:
        self.errors = errors


def _uuid(value: Any, field: str, errors: list[Error]) -> str | None:
    if not isinstance(value, str):
        errors.append(Error("INVALID_FIELD", f"{field} must be a string."))
        return None
    try:
        return str(UUID(value))
    except ValueError:
        errors.append(Error("INVALID_UUID", f"{field} is not a valid UUID."))
        return None


def _amount(value: Any, field: str, errors: list[Error]) -> int | None:
    if not isinstance(value, str):
        errors.append(Error("INVALID_FIELD", f"{field} must be a string."))
        return None
    if not AMOUNT.fullmatch(value):
        errors.append(
            Error("INVALID_AMOUNT", f"{field} is not a positive dollar amount.")
        )
        return None
    dollars, dot, fraction = value.partition(".")
    cents = int(dollars) * 100 + int(fraction.ljust(2, "0") if dot else 0)
    if not 0 < cents <= INTEGER_MAX:
        errors.append(
            Error("INVALID_AMOUNT", f"{field} is outside the supported range.")
        )
        return None
    return cents


def validate_request(body: Any, settings: Settings) -> BulkPayment:
    if not isinstance(body, dict):
        raise InvalidRequest(
            [Error("INVALID_FIELD", "Request body must be an object.")]
        )
    data = cast(dict[str, Any], body)

    errors: list[Error] = []
    payer = _uuid(data.get("payer_firm_uuid"), "payer_firm_uuid", errors)
    raw_payments_value = data.get("payments")
    if not isinstance(raw_payments_value, list):
        errors.append(Error("INVALID_FIELD", "payments must be an array."))
        raw_payments: list[Any] = []
    else:
        raw_payments = cast(list[Any], raw_payments_value)
    if isinstance(raw_payments_value, list) and not raw_payments:
        errors.append(Error("EMPTY_PAYMENTS", "payments must not be empty."))
    elif (
        isinstance(raw_payments_value, list)
        and len(raw_payments) > settings.max_payments
    ):
        errors.append(Error("INVALID_FIELD", "payments exceeds the configured limit."))

    payments: list[Payment] = []
    for index, item in enumerate(raw_payments):
        field = f"payments[{index}]"
        if not isinstance(item, dict):
            errors.append(Error("INVALID_FIELD", f"{field} must be an object."))
            continue
        payment_data = cast(dict[str, Any], item)
        payee = _uuid(
            payment_data.get("payee_firm_uuid"), f"{field}.payee_firm_uuid", errors
        )
        cents = _amount(payment_data.get("amount"), f"{field}.amount", errors)
        description = payment_data.get("description")
        if not isinstance(description, str):
            errors.append(
                Error("INVALID_FIELD", f"{field}.description must be a string.")
            )
        elif len(description) > settings.max_description_length:
            errors.append(Error("INVALID_FIELD", f"{field}.description is too long."))
        if payer is not None and payee == payer:
            errors.append(Error("SELF_PAYMENT", f"{field} pays the payer firm."))
        if payee is not None and cents is not None and isinstance(description, str):
            payments.append(Payment(payee, cents, description))

    if sum(payment.amount_cents for payment in payments) > INTEGER_MAX:
        errors.append(
            Error("INVALID_AMOUNT", "Payment total exceeds the supported range.")
        )
    if errors:
        raise InvalidRequest(errors)
    if payer is None:  # pragma: no cover - an invalid payer always adds an error
        raise RuntimeError("validated request has no payer")
    return BulkPayment(payer, payments)
