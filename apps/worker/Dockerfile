FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app/api-src

WORKDIR /app
RUN groupadd --system --gid 10001 ltc \
    && useradd --system --uid 10001 --gid ltc --home-dir /nonexistent ltc
COPY --chown=ltc:ltc src ./src
COPY --from=ltc_api --chown=ltc:ltc src/ltc ./api-src/ltc
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --timeout 180 --retries 5 -r requirements.txt
RUN mkdir -p /tmp/ltc/meetings && chown ltc:ltc /tmp/ltc/meetings
USER ltc
CMD ["python", "-m", "ltc_worker.main"]

FROM runtime AS test
USER root
COPY --chown=ltc:ltc tests ./tests
USER ltc
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
