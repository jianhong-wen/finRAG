# One command for every check: make check
.PHONY: check lint typecheck test

check: lint typecheck test

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy

test:
	pytest --cov --cov-report=term-missing
