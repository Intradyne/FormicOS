"""Formic-OS entry point. Starts the API server."""

import uvicorn


def main() -> None:
    uvicorn.run(
        "src.server:app_factory",
        factory=True,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
