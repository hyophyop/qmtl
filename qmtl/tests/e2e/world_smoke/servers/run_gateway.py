"""Run the Gateway app with WebSocketHub enabled and a WorldService URL.

Environment:
- WORLDS_BASE_URL: base URL for the stub/real WorldService
- GATEWAY_HOST (optional): default 0.0.0.0
- GATEWAY_PORT (optional): default 8000
"""

from __future__ import annotations

import os
import uvicorn

from qmtl.services.gateway.api import create_app
from qmtl.services.gateway.ws import WebSocketHub


def main() -> None:
    ws_url = os.environ.get("WORLDS_BASE_URL")
    host = os.environ.get("GATEWAY_HOST", "0.0.0.0")
    port = int(os.environ.get("GATEWAY_PORT", "8000"))
    app = create_app(
        ws_hub=WebSocketHub(),
        worldservice_url=ws_url,
        enable_worldservice_proxy=True,
        enable_background=False,
        database_backend="sqlite",
        database_dsn=":memory:",
        enforce_live_guard=False,
    )
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

