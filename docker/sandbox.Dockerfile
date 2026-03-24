# Minimal Python sandbox for code_execute tool.
# No pip packages — standard library only.
# Run with: --read-only --network=none --memory=256m --cpus=0.5 --tmpfs /tmp:size=10m
FROM python:3.12-slim

RUN useradd -m -s /bin/bash sandbox
USER sandbox
WORKDIR /code

ENTRYPOINT ["python"]
