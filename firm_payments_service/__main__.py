import uvicorn

from firm_payments_service.logging_config import logging_config
from firm_payments_service.settings import Settings

if __name__ == "__main__":
    settings = Settings()
    uvicorn.run(
        "firm_payments_service.main:app",
        host="0.0.0.0",  # nosec B104: Compose publishes only on localhost.
        port=8000,
        reload=settings.reload,
        log_config=logging_config(settings.log_level),
    )
