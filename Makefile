.PHONY: dev test lint demo train seed verify-outputs

dev:
	@docker compose up --build

test:
	@uv run --isolated --project backend --extra test pytest backend/tests
	@uv run --isolated --project telegram_bot --extra test pytest telegram_bot/tests
	@uv run --isolated --project mock_portal --extra test pytest mock_portal/tests

lint:
	@uv run --isolated --project backend --extra test ruff check backend telegram_bot mock_portal

demo:
	@uv run --isolated --project backend python scripts/run_demo.py

train:
	@python ml_training/train.py

seed:
	@uv run --isolated --project backend python scripts/seed.py

verify-outputs:
	@uv run --project backend python scripts/verify_outputs.py
