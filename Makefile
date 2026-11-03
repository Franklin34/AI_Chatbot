.PHONY: install run test lint format docker

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt

run:
	.venv/bin/uvicorn app.main:app --reload

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check . && .venv/bin/ruff format --check .

format:
	.venv/bin/ruff check --fix . && .venv/bin/ruff format .

docker:
	docker compose up --build
