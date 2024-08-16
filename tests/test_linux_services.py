import json
import re


def test_journal_warnings(shell):
    stdout = shell.run_check(
        "journalctl -b -k --output json --prio 4 --output-fields=MESSAGE | cat"
    )  # use cat to avoid colors
    entries = []
    for line in stdout:
        entries.append(json.loads(line))

    whitelist = [
        r"spi_stm32 44009000\.spi: failed to request tx dma channel",
        r"spi_stm32 44009000\.spi: failed to request rx dma channel",
        r"clk: failed to reparent ethck_k to pll4_p: -22",
        r"stm32_rtc 5c004000\.rtc: Date\/Time must be initialized",
        r"File \/var\/log\/journal\/.*\/system.journal corrupted or uncleanly shut down, renaming and replacing.",
        r"stm32-dwmac 5800a000\.ethernet switch: Adding VLAN ID 0 is not supported",
        # The following messages can be present if the USB stick is connected:
        r"sd 0:0:0:0: \[sda\] No Caching mode page found",
        r"sd 0:0:0:0: \[sda\] Assuming drive cache: write through",
        r"block sda: the capability attribute has been deprecated.",
    ]

    whitelist = [re.compile(r) for r in whitelist]

    remaining = []

    for entry in entries:
        for whitelist_entry in whitelist:
            if whitelist_entry.match(entry["MESSAGE"]):
                break
        else:
            remaining.append(entry["MESSAGE"])

    assert remaining == []


def test_systemd_journald(shell):
    """
    Test if systemd-journald is installed and running.
    """

    shell.run_check("pidof systemd-journald")


def test_klogd(shell):
    """klogd should not be installed"""
    _, _, returncode = shell.run("[ -e /sbin/klogd ]")
    assert returncode != 0

    _, _, returncode = shell.run('ps | grep "[k]logd"')
    assert returncode != 0  # grep returns 0 if matching lines are found


def test_syslogd(shell):
    """syslog should not be installed"""
    _, _, returncode = shell.run("[ -e /sbin/syslogd ]")
    assert returncode != 0

    _, _, returncode = shell.run('ps | grep "[s]yslogd"')
    assert returncode != 0  # grep returns 0 if matching lines are found


def test_dbus(shell):
    """
    Test dbus by running `busctl list`.
    """

    out = shell.run_check("busctl --json=short list")
    found_bus_names = set()
    for peer in json.loads("".join(out)):
        if peer["name"].startswith(":"):
            continue
        found_bus_names.add(peer["name"])

    expected_bus_names = {
        "de.pengutronix.rauc",
        "de.pengutronix.tacd",
        "org.freedesktop.DBus",
        "org.freedesktop.NetworkManager",
        "org.freedesktop.nm_dispatcher",
        "org.freedesktop.systemd1",
        "org.freedesktop.Avahi",
    }

    optional_bus_names = {
        "org.freedesktop.machine1",
        "org.freedesktop.timesync1",
        "org.freedesktop.locale1",
        "org.freedesktop.timedate1",
        "org.freedesktop.hostname1",
        "org.freedesktop.login1",
        "org.freedesktop.resolve1",
        "org.freedesktop.network1",
        "fi.w1.wpa_supplicant1",
        "org.bluez",
        "org.freedesktop.PolicyKit1",
        "org.freedesktop.UDisks2",
        "org.freedesktop.nm_priv_helper",
    }

    assert found_bus_names - optional_bus_names == expected_bus_names
