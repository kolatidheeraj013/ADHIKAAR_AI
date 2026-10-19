.PHONY: dev test lint demo train seed

dev:
	@docker compose up --build

test:
	@python -m pytest backend/tests
	@python -m pytest telegram_bot/tests
	@python -m pytest mock_portal/tests

lint:
	@ruff check backend telegram_bot mock_portal

demo:
	@python scripts/run_demo.py

train:
	@python ml_training/train.py

seed:
	@python scripts/seed.py
