FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONPATH=/app/src

WORKDIR /app
RUN groupadd --system --gid 10001 ltc \
    && useradd --system --uid 10001 --gid ltc --home-dir /nonexistent ltc
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS runtime
COPY --chown=ltc:ltc src ./src
RUN mkdir -p /app/data /tmp/ltc/meetings && chown ltc:ltc /app/data /tmp/ltc/meetings
USER ltc
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "ltc.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test
USER root
RUN pip install --no-cache-dir httpx==0.28.1
COPY --chown=ltc:ltc tests ./tests
USER ltc
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
