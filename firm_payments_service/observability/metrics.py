from fastapi import Depends, FastAPI
from prometheus_fastapi_instrumentator import Instrumentator, metrics

from firm_payments_service.auth import require_operational_key


def register_metrics(app: FastAPI) -> None:
    # The library leaves custom_labels untyped.
    Instrumentator().add(metrics.default()).add(  # pyright: ignore[reportUnknownMemberType]
        metrics.latency(  # pyright: ignore[reportUnknownMemberType]
            metric_name="http_request_duration_by_status_seconds"
        )
    ).instrument(app).expose(
        app, include_in_schema=False, dependencies=[Depends(require_operational_key)]
    )
