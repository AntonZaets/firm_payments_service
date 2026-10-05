from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from polyfactory.factories import DataclassFactory

Payload = dict[str, Any]


def random_uuid() -> str:
    return str(uuid4())


@dataclass
class Firm:
    id: int
    name: str
    balance_cents: int
    uuid: str


@dataclass
class Payment:
    payee_firm_uuid: str
    amount: str
    description: str


@dataclass
class BulkRequest:
    payer_firm_uuid: str
    payments: list[Payment]


class FirmFactory(DataclassFactory[Firm]):
    __model__ = Firm
    uuid = staticmethod(random_uuid)
    balance_cents = 100_000


class PaymentFactory(DataclassFactory[Payment]):
    __model__ = Payment
    payee_firm_uuid = staticmethod(random_uuid)
    amount = "1.00"


class BulkRequestFactory(DataclassFactory[BulkRequest]):
    __model__ = BulkRequest


def request_for(payer: Firm, *payments: Payment) -> Payload:
    return asdict(
        BulkRequestFactory.build(payer_firm_uuid=payer.uuid, payments=list(payments))
    )
