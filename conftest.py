import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--lab-db-env",
        default=None,
        help="Env file with POSTGRES_* settings for the lab database. Without it, database "
        "tests are skipped.",
    )
