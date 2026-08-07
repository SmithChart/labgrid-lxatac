import contextlib
import traceback
from time import monotonic

import pytest

pytest_plugins = ["postmortem"]


@pytest.fixture(scope="function")
def barebox(strategy):
    try:
        strategy.transition("barebox")
    except Exception as e:
        traceback.print_exc()
        pytest.exit(f"Transition into barebox failed: {e}", returncode=3)

    return strategy.barebox


@pytest.fixture(scope="function")
def shell(strategy):
    try:
        strategy.transition("shell")
    except Exception as e:
        traceback.print_exc()
        pytest.exit(f"Transition into shell failed: {e}", returncode=3)

    return strategy.shell


@pytest.fixture
def rauc_bundle(target, strategy, env, shell):
    """Makes the RAUC bundle target-accessible at the returned location."""
    bundle = env.config.get_image_path("rauc_bundle")

    def _rauc_bundle():
        target.activate(strategy.httpprovider)
        return strategy.httpprovider.stage(bundle)

    yield _rauc_bundle


@pytest.fixture
def eet(strategy):
    eet = strategy.eet
    yield eet
    if eet:
        eet.link("")


@pytest.fixture(scope="function")
def log_duration(record_property):
    """
    Allows to log the duration of a context as a property of the executed test.
    This can be used to measure the duration of specific commands and write the result to the junitXML.
    Use this fixture as a context manager:
    > with log_duration("property-name"):
    >     time.sleep(1)
    """

    @contextlib.contextmanager
    def duration_logger(name: str):
        start = monotonic()
        yield
        record_property(name, monotonic() - start)

    return duration_logger


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: These tests run especially slow.")
