.PHONY: install test lint clean help

help:
	@echo "Available commands:"
	@echo "  install   - Install project dependencies using Poetry"
	@echo "  test      - Run tests using pytest within the Poetry environment"
	@echo "  lint      - Run linters (e.g., flake8, black, mypy - requires setup)"
	@echo "  clean     - Remove build artifacts and cache files"

install:
	poetry install

test:
	poetry run pytest src/

lint:
	@echo "Linting... (Remember to use 'poetry run ...')"
	# Add linting commands here, e.g.:
	# poetry run flake8 src/mux tests
	# poetry run black --check src/mux tests
	# poetry run mypy src/mux

clean:
	@echo "Cleaning up..."
	find . -type f -name '*.py[co]' -delete
	find . -type d -name '__pycache__' -delete
	rm -rf build dist *.egg-info .pytest_cache .coverage htmlcov .mypy_cache
	rm -rf .tox .nox

