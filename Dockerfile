FROM node:22-slim AS frontend-builder

WORKDIR /app

COPY frontend/package*.json frontend/
RUN cd frontend && npm ci

COPY frontend frontend
RUN mkdir -p gw/web/static && cd frontend && npm run build

FROM python:3.12-slim AS wheel-builder

WORKDIR /app

COPY pyproject.toml README.md MANIFEST.in ./
COPY gw gw
COPY --from=frontend-builder /app/gw/web/static gw/web/static
RUN python -m pip wheel --no-cache-dir --no-deps --wheel-dir /wheels .

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV GW_BACKEND_HOST=0.0.0.0
ENV GW_BACKEND_PORT=8000

COPY --from=wheel-builder /wheels/*.whl /tmp/
RUN python -m pip install --no-cache-dir /tmp/*.whl && \
    rm -f /tmp/*.whl

EXPOSE 8000

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
