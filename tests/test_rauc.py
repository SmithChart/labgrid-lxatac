import json

import pytest

from lxatacstrategy import LXATACStrategy

"""
Basic rauc tests

These tests check how rauc and bootchooser work together to install updates.
These tests are allowed to install a new system in slot 1 (or even break a system in slot 1), as long as they leave
slot 0 intact.
Each test can change the bootstate and boot into another system using the `set_bootstate_in_bootloader` fixture and
also boot into slot 1.
They do not need to reboot the system into slot 0. This is implicitly done via the `default_bootstate` fixture, that
is already a dependency of `set_bootstate_in_bootloader`.
"""

# TODO: We need to define how we want to handle situations where no slot has boot attempts left
#  and write a test for that.


@pytest.fixture
def default_bootstate(strategy: LXATACStrategy):
    """
    Set default state values as setup/teardown

    Note: This fixture changes the state of the DUT using the strategy.
    When using this fixture do not rely on fixtures like "shell" to define the DUT's state.
    Always ensure the state manually by calling strategy.transition() is needed.
    """
    strategy.transition("barebox")
    strategy.barebox.run_check("bootchooser -a default -p default")

    yield

    strategy.transition("barebox")
    strategy.barebox.run_check("bootchooser -a default -p default")


@pytest.fixture
def booted_slot(strategy: LXATACStrategy):
    """
    Returns booted slot

    Note: Calling the Callable returned by this fixture will transition the DUT in the "shell" state.
    """

    def _booted_slot():
        strategy.transition("shell")
        [stdout] = strategy.shell.run_check("rauc status --output-format=json", timeout=60)
        rauc_status = json.loads(stdout)

        assert "booted" in rauc_status, 'No "booted" key in rauc status JSON found'

        return rauc_status["booted"]

    yield _booted_slot


@pytest.fixture
def set_bootstate_in_bootloader(strategy: LXATACStrategy, default_bootstate):
    """
    Sets the given bootchooser parameters

    Note: This fixture changes the state of the DUT using the strategy.
    When using this fixture do not rely on fixtures like "shell" to define the DUT's state.
    Always ensure the state manually by calling strategy.transition() is needed.
    """

    def _set_bootstate(system0_prio, system0_attempts, system1_prio, system1_attempts):
        strategy.transition("barebox")
        barebox = strategy.barebox

        barebox.run_check(f"state.bootstate.system0.priority={system0_prio}")
        barebox.run_check(f"state.bootstate.system0.remaining_attempts={system0_attempts}")

        barebox.run_check(f"state.bootstate.system1.priority={system1_prio}")
        barebox.run_check(f"state.bootstate.system1.remaining_attempts={system1_attempts}")

        barebox.run_check("state -s")

    yield _set_bootstate


def test_rauc_version(shell):
    """
    Test basic availability working of rauc binary by obtaining version
    information
    """
    stdout = shell.run_check("rauc --version")
    assert "rauc" in "\n".join(stdout)


def test_rauc_status(shell):
    """
    Test basic slot status readout.
    """
    shell.run_check("rauc status", timeout=60)


def test_rauc_info_json(shell, rauc_bundle, check):
    """
    Test rauc info output in JSON for a rauc bundle read via http.
    """
    # Let rauc read the info for the rauc bundle.
    # The diversion via the tmp-file allows us to ignore any output on stderr that rauc may output.
    shell.run_check(f"rauc info {rauc_bundle()} --output-format=json > /tmp/rauc.json")
    result = shell.run_check("cat /tmp/rauc.json")
    result = json.loads("\n".join(result))

    # Check if the bundle contains the metadata that we expect.
    with check:
        assert result["compatible"] == "Linux Automation GmbH - LXA TAC"
    with check:
        assert len(result["hooks"]) == 0, "There shouldn't be any hooks in the bundles"
    with check:
        assert len(result["images"]) == 2, 'The bundles should contain two images ("bootloader" & "rootfs")'
    with check:
        assert "rootfs" in result["images"][0], 'First image in bundle should be "rootfs"'
    with check:
        assert "bootloader" in result["images"][1], 'Second image in bundle should be "bootloader"'


@pytest.mark.slow
@pytest.mark.dependency()
def test_rauc_install(strategy, booted_slot, set_bootstate_in_bootloader, rauc_bundle, log_duration):
    """
    Test if a rauc install from slot0 into slot1 works.
    """

    # Make sure we are in slot 0
    set_bootstate_in_bootloader(20, 1, 10, 1)
    strategy.transition("shell")
    assert booted_slot() == "system0"

    # Actual installation - may take a few minutes.
    # Thus, let's use a large timeout.
    with log_duration("rauc install duration"):
        strategy.shell.run_check(f"rauc install {rauc_bundle()}", timeout=600)

    # Power cycle and reboot into the new system.
    strategy.transition("off")
    strategy.transition("shell")
    assert booted_slot() == "system1"


@pytest.mark.slow
@pytest.mark.dependency(depends=["test_rauc_install"])
def test_bootchooser_boot_system0_and_mark_bad(strategy, booted_slot, set_bootstate_in_bootloader):
    """
    Test if booting by priority works.

    To archive this mark system slot0 bad and test fallback.
    """
    set_bootstate_in_bootloader(20, 1, 10, 1)
    strategy.transition("shell")
    shell = strategy.shell
    assert booted_slot() == "system0"

    # mark system0 bad
    shell.run_check("rauc status mark-bad")

    # Power cycle and reboot.
    # Since slot0 is now bad, bootchooser should boot into slot1.
    strategy.transition("off")
    strategy.transition("shell")
    assert booted_slot() == "system1"


@pytest.mark.slow
@pytest.mark.dependency(depends=["test_rauc_install"])
def test_bootchooser_boot_system1_and_mark_bad(strategy, booted_slot, set_bootstate_in_bootloader):
    """
    Test if booting by priority works.

    To archive this mark system slot1 bad and test fallback.
    """
    set_bootstate_in_bootloader(10, 1, 20, 1)
    strategy.transition("shell")
    shell = strategy.shell
    assert booted_slot() == "system1"

    # mark system1 bad
    shell.run_check("rauc status mark-bad")

    # Power cycle and reboot.
    # Since slot1 is now bad, bootchooser should boot into slot0.
    strategy.transition("off")
    strategy.transition("shell")
    assert booted_slot() == "system0"


@pytest.mark.slow
def test_bootchooser(barebox, check):
    """Test if bootchooser in barebox works."""
    stdout = barebox.run_check("bootchooser -i")
    with check:
        assert stdout[0].startswith("Good targets")
    with check:
        assert stdout[1] != "none"
