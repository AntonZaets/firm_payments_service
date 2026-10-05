import pytest
from fastapi.testclient import TestClient

from .conftest import ENDPOINT, Failure, Snapshot
from .factories import Firm, Payload

pytestmark = [pytest.mark.just_contract, pytest.mark.usefixtures("existing_records")]


@pytest.mark.parametrize("table", ["payments", "firm_payments_audit"])
def test_database_failure_rolls_back(
    client: TestClient,
    transfer_case: tuple[list[Firm], Payload],
    database_snapshot: Snapshot,
    database_failure: Failure,
    table: str,
) -> None:
    _, payload = transfer_case
    if table == "payments":
        payload["payments"][1]["description"] = "reject-this-payment"
    database_failure(table)
    before = database_snapshot()
    response = client.post(ENDPOINT, json=payload)
    assert response.status_code == 500, response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert "private database failure" not in response.text
    assert database_snapshot() == before
