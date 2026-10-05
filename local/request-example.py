"""Submit the PDF example using a freshly issued local Dex ID token."""

import argparse
import base64
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--token-url", default="http://localhost:5556/dex/token")
    args = parser.parse_args()
    credentials = base64.b64encode(
        b"firm-payments:local-payment-client-secret"
    ).decode()
    token_request = Request(
        args.token_url,
        data=urlencode(
            {
                "grant_type": "password",
                "username": "payer@example.test",
                "password": "password",
                "scope": "openid federated:id",
            }
        ).encode(),
        headers={"Authorization": f"Basic {credentials}"},
    )
    try:
        with urlopen(token_request, timeout=30) as response:
            token = json.load(response)["id_token"]
        request = Request(
            f"{args.api_url.rstrip('/')}/api/v1/payments/bulk",
            data=Path(__file__).with_name("payment.json").read_bytes(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=60) as response:
            print(f"HTTP {response.status}")
            print(response.read().decode())
            return 0 if response.status == 201 else 1
    except HTTPError as error:
        print(f"HTTP {error.code}", file=sys.stderr)
        print(error.read().decode(), file=sys.stderr)
    except (URLError, TimeoutError, KeyError, ValueError) as error:
        print(f"Sample request failed: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
