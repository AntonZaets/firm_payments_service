from fastapi import Depends, FastAPI
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator, metrics

from firm_payments_service.auth import require_operational_key

payment_batches = Counter(
    "payment_batches_total",
    "Bulk payment requests by outcome.",
    ("outcome",),
)
payment_transaction_failures = Counter(
    "payment_transaction_failures_total",
    "Bulk payment database transaction failures by reason.",
    ("reason",),
)


def register_metrics(app: FastAPI) -> None:
    # The library leaves custom_labels untyped.
    Instrumentator().add(metrics.default()).add(  # pyright: ignore[reportUnknownMemberType]
        metrics.latency(  # pyright: ignore[reportUnknownMemberType]
            metric_name="http_request_duration_by_status_seconds"
        )
    ).instrument(app).expose(
        app, include_in_schema=False, dependencies=[Depends(require_operational_key)]
    )


def record_payment_batch(outcome: str) -> None:
    payment_batches.labels(outcome).inc()


def record_payment_transaction_failure(reason: str) -> None:
    payment_transaction_failures.labels(reason).inc()
