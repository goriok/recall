# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python .

# --- runtime ---
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    RECALL_IN_CONTAINER=1

RUN groupadd --system --gid 1000 recall \
    && useradd  --system --uid 1000 --gid 1000 --create-home --home-dir /home/recall recall \
    && mkdir -p /config /sources /analysis /home/recall/.cache/recall/logs \
    && chown -R recall:recall /config /home/recall

COPY --from=builder /opt/venv /opt/venv

USER recall
WORKDIR /config

ENTRYPOINT ["recall"]
CMD ["scheduler", "run"]
