COMPOSE = docker compose -p $${LTC_COMPOSE_PROJECT_NAME:-ltc-v36}

.PHONY: api-run api-test build contract-test db-init db-up db-down db-verify logs test up web-build web-dev web-install worker-test

build:
	$(COMPOSE) build api web worker
	$(COMPOSE) --profile test build worker-test

db-up:
	$(COMPOSE) up -d postgres

db-init:
	./scripts/init_database.sh

up: db-init
	$(COMPOSE) up -d --build api web worker

api-run: db-init
	$(COMPOSE) up --build api worker

web-install:
	$(COMPOSE) build web

web-dev: db-init
	$(COMPOSE) up --build web worker

contract-test:
	$(COMPOSE) --profile test run --rm contract-test

api-test:
	$(COMPOSE) --profile test run --rm --build api-test

worker-test:
	$(COMPOSE) --profile test run --rm --build worker-test

web-build:
	$(COMPOSE) --profile test run --rm --build web-test

db-verify:
	$(COMPOSE) --profile test run --rm --build database-test

test: contract-test api-test worker-test web-build db-verify

logs:
	$(COMPOSE) logs -f api web worker postgres

db-down:
	$(COMPOSE) down
