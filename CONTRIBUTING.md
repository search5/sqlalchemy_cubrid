# Contributing to sqlalchemy-cubrid

Thank you for your interest in contributing!

## Development Setup

```bash
# Clone the repository
git clone https://github.com/search5/sqlalchemy_cubrid.git
cd sqlalchemy_cubrid

# Install dependencies
poetry install

# Start CUBRID (Docker)
docker-compose up -d

# Run tests
poetry run pytest tests/ --ignore=tests/test_suite.py
```

## Code Quality

We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting, enforced via pre-commit:

```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run manually
ruff check sqlalchemy_cubrid/
ruff format sqlalchemy_cubrid/
```

## Testing

- All changes must pass the existing test suite
- New features should include tests in `tests/`
- Tests run against CUBRID 10.2, 11.0, 11.2, 11.3, and 11.4

### Running specific test files

```bash
poetry run pytest tests/test_types.py -v
```

### Running against a different CUBRID version

```bash
CUBRID_TEST_URL="cubrid://dba:@localhost:33002/testdb" poetry run pytest tests/ --ignore=tests/test_suite.py
```

## Pull Request Process

1. Fork the repository and create a feature branch
2. Make your changes with tests
3. Ensure `ruff check` and `ruff format --check` pass
4. Submit a PR with a clear description

## Commit Messages

- Use imperative mood ("Add feature" not "Added feature")
- Keep the first line under 72 characters
- Reference issues with `#123` where applicable

## Reporting Bugs

Please use the [bug report template](https://github.com/search5/sqlalchemy_cubrid/issues/new?template=bug_report.md) and include:

- Python, SQLAlchemy, CUBRID, and pycubrid versions
- Minimal reproducible code
- Full traceback

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
