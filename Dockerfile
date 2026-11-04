FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements-hosted.lock ./requirements-hosted.lock
RUN pip install --no-cache-dir -r requirements-hosted.lock
# Intentionally copy source and the public company catalog, not the whole tree.
# data/jobs.db, private snapshots, .venv, .work and .env are not image inputs.
COPY src ./src
COPY scripts/init_hosted.py ./scripts/init_hosted.py
COPY data/finnish_companies.json ./data/finnish_companies.json
RUN python -m compileall -q src scripts/init_hosted.py \
    && useradd --system --uid 10001 jobhunt \
    && chown -R jobhunt:jobhunt /app
USER jobhunt
EXPOSE 3000
# Preparation is additive and idempotent; it never imports the local SQLite data.
# Raw request URLs can contain OAuth codes; do not write them to access logs.
CMD ["sh", "-c", "python scripts/init_hosted.py && exec python -m uvicorn src.hosted.app:app --host 0.0.0.0 --port ${PORT:-3000} --no-access-log"]
