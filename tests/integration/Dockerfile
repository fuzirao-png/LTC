FROM python:3.11-alpine AS test

RUN apk add --no-cache docker-cli
RUN pip install --no-cache-dir psycopg[binary]==3.2.9
ENTRYPOINT ["python", "scripts/verify_database.py"]
