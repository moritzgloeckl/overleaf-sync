"""Shared pytest configuration. Unit tests run by default; see pyproject.toml for the markers."""


def pytest_addoption(parser):
    parser.addoption("--keep-ce", action="store_true",
                     help="Keep the Overleaf CE containers running after the integration tests")
