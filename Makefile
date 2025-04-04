.PHONY: install test lint clean help

help:
	@echo "Available commands:"
	@echo "  install   - Install the package in editable mode"
	@echo "  test      - Run tests using pytest"
	@echo "  lint      - Run linters (e.g., flake8, black, mypy - requires setup)"
	@echo "  clean     - Remove build artifacts and cache files"

install:
	pip install -e .

test:
	pytest src/

lint:
	@echo "Linting..."
	# Add linting commands here, e.g.:
	# flake8 src/mux tests
	# black --check src/mux tests
	# mypy src/mux

clean:
	@echo "Cleaning up..."
	find . -type f -name '*.py[co]' -delete
	find . -type d -name '__pycache__' -delete
	rm -rf build dist *.egg-info .pytest_cache .coverage htmlcov .mypy_cache
	rm -rf .tox .nox

