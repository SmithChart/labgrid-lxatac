import csv
import json
import re
from dataclasses import dataclass

import labgrid
import pytest
import requests


def test_chrony(shell):
    """Test that chronyd is running and synchronized."""
    stdout = shell.run_check("chronyc -c tracking")
    csv_reader = csv.reader(stdout)

    for line in csv_reader:
        # make sure stratum > 0 is used
        assert int(line[2]) > 0


def test_switch_configuration(shell, check):
    """Test that the switch is configured correctly."""
    uplink_ifname = "uplink"

    [bridge] = shell.run_check("bridge -j link")
    bridge_json = json.loads(bridge)

    # interface exists
    assert any(b["ifname"] == uplink_ifname for b in bridge_json)

    # interface is in expected state
    for b in bridge_json:
        if b["ifname"] == uplink_ifname:
            assert b["state"] == "forwarding"

    [ip_link] = shell.run_check("ip -d -j link show tac-bridge")
    [ip_link_json] = json.loads(ip_link)

    # link attributes are in expected state
    with check:
        assert ip_link_json["linkinfo"]["info_data"]["stp_state"] == 0
    with check:
        assert ip_link_json["linkinfo"]["info_data"]["mcast_snooping"] == 0

    [ip_addr] = shell.run_check("ip -d -j addr show tac-bridge")
    [ip_addr_json] = json.loads(ip_addr)

    mac = ip_addr_json["address"]
    link_local_v6 = next(
        ai["local"] for ai in ip_addr_json["addr_info"] if ai["family"] == "inet6" and ai["scope"] == "link"
    )
    global_v6 = next(
        ai["local"] for ai in ip_addr_json["addr_info"] if ai["family"] == "inet6" and ai["scope"] == "global"
    )

    # Each TAC is assigned 16 MAC addresses and the tac-bridge should use
    # the one ending in '3'.
    with check:
        assert mac[-1] == "3"

    # Check if the configured v6 addresses are derived from the current MAC address.
    v6_tail = mac.split(":")
    v6_tail.insert(3, "fe")
    v6_tail.insert(3, "ff")
    v6_tail = list(int(a + b, 16) for a, b in zip(v6_tail[::2], v6_tail[1::2], strict=True))
    v6_tail[0] ^= 0x0200
    v6_tail = ":".join(f"{a:x}" for a in v6_tail)

    with check:
        assert link_local_v6.endswith(v6_tail)
    with check:
        assert global_v6.endswith(v6_tail)

    # Check if we have at least one dynamic IPv4 address on tac-bridge
    with check:
        v4_addrs = [
            ai["local"]
            for ai in ip_addr_json["addr_info"]
            if ai["family"] == "inet" and "dynamic" in ai and ai["dynamic"]
        ]
        assert len(v4_addrs), "No IPv4 addr configured via DHCP"


def test_hostname(shell, check):
    """Test whether the serial number is contained in the hostname"""

    [serial_number] = shell.run_check("cat /sys/firmware/devicetree/base/chosen/baseboard-factory-data/serial-number")
    serial_number = serial_number.rstrip("\x00")  # Remove trailing \0
    serial_number = serial_number.split(".")[-1]  # Only the last part is used in the hostname

    [hostname] = shell.run_check("hostname")

    with check:
        assert serial_number in hostname

    [etc_hostname] = shell.run_check("cat /etc/hostname")

    with check:
        assert etc_hostname != "localhost"

    with check:
        assert serial_number in etc_hostname


def test_system_running(shell):
    """
    Test if the system state is running.
    """

    # This will exit non-zero if we have any other state than "running", but we are interested in the string output.
    # So let's ignore the returncode.
    [state], _, _ = shell.run("systemctl is-system-running")

    assert state == "running"


@pytest.fixture
def clocktree(shell):
    """
    Read the clock tree from the DUT and parse it into a data structure.
    """
    re_entry = re.compile(r"^\s*(\S+)\s+\d+\s+\d+\s+\d+\s+(\d+)\s+\d+\s+\d+\s+(\d+)\s+\S\s+(\S+)\s+")
    re_2nd = re.compile(r"^\s+(\S+)\s+\S+\s+$")

    @dataclass
    class Clk:
        clk_name: str
        rate: int
        duty: int
        consumer: list

    clks = {}
    clk = None
    for line in shell.run_check("cat /sys/kernel/debug/clk/clk_summary"):
        if match := re_entry.match(line):
            if clk:
                clks[clk.clk_name] = clk
            clk = Clk(clk_name=match.group(1), rate=int(match.group(2)), duty=int(match.group(3)), consumer=[])
            if match.group(4) != "deviceless":
                clk.consumer.append(match.group(4))
            continue

        match = re_2nd.match(line)
        if match and match.group(1) != "deviceless":
            clk.consumer.append(match.group(1))

    return clks


@pytest.mark.parametrize(
    "clock_name, rate, consumer",
    (
        # Ethernet Clocks: Needed for the communication with the phy to work
        ("ethptp_k", 125000000, ("5800a000.ethernet",)),
        ("ethck_k", 125000000, ("5800a000.ethernet",)),
        ("ethrx", 125000000, ("5800a000.ethernet",)),
        # CAN Clock: Chosen to be 48MHz for minimum baudrate error across all rates
        ("fdcan_k", 48000000, ("4400f000.can", "4400e000.can")),
    ),
)
def test_clocktree(clocktree, check, clock_name, rate, consumer):
    """
    Make sure a few selected devices have their fixed clock rates applied.
    In this test we check the association of the clock signal with the actual
    device and the clocks rate.
    """
    assert clock_name in clocktree

    clk = clocktree[clock_name]

    with check:
        assert clk.rate == rate

    for c in consumer:
        with check:
            assert c in clk.consumer


@pytest.mark.lg_feature("ptx-flavor")
def test_ptx_ssh_keys(shell):
    """
    Check if there is at least one SSH key in the auto-generated authorized_keys.
    This file is generated in our internal flavor of meta-lxatac and contains all relevant keys from our ansible.
    """
    shell.run_check('grep -q "^ssh-" /etc/ssh/authorized_keys.root')


def test_ssh_password_login_disabled(shell, strategy):
    """
    Check if the sshd running on the LXA TAC offers only "publickey" as authentication method.

    @relation(CYSEC-1, scope=function)
    """
    auth_methods = shell.run_check(
        "ssh -v -o PreferredAuthentications=none -o UserKnownHostsFile=/dev/null -o "
        f"StrictHostKeyChecking=no root@{strategy.network.address} 2>&1 | grep Authentications"
    )
    assert "debug1: Authentications that can continue: publickey" in [x.strip() for x in auth_methods]


def test_ssh_no_pubkeys(shell, env: labgrid.Environment, check):
    """
    Make sure there are no SSH pubkeys present on the device.
    This test aims to find ssh pubkeys that have been left on the device by accident, so we only check the most likely
    locations in the file system.

    @relation(CYSEC-2, scope=function)
    """

    if "ptx-flavor" in env.get_target_features():
        pytest.skip(reason="Test does not make sense for non-production image with ptx-flavor.")

    # Check for authorized keys for all users.
    # This way we can later add new users and this test will automatically pick them up.
    homes = shell.run_check("cat /etc/passwd | cut -d':' -f 6")
    for home in homes:
        with check:
            shell.run_check(f"test ! -f {home}/.ssh/authorized_keys")

    # Check for the authorized keys from the ptx-flavor.
    with check:
        shell.run_check("test ! -f /etc/ssh/authorized_keys.root")


def test_iobus_website(shell, strategy):
    """
    Test if the LXA IOBus server serves it's website.
    """
    r = requests.get(f"http://{strategy.network.address}:8080")
    assert r.status_code == 200
    assert "<title>LXA IOBus Server</title>" in r.text


def test_iobus_server_state(shell, strategy, check):
    """
    Test if the LXA IOBus server reports a useful state.

    In the test fixture there is no LXA IOBus node connected to the LXA TAC.
    Thus can_tx_state will be "error" - but everything else should look normal.
    """
    r = requests.get(f"http://{strategy.network.address}:8080/server-info/")
    assert r.status_code == 200

    state = json.loads(r.text)

    [hostname] = shell.run_check("hostname")

    with check:
        assert "hostname" in state and state["hostname"] == hostname

    with check:
        assert "can_interface" in state and state["can_interface"] == "can0_iobus"

    with check:
        assert "can_interface_is_up" in state and state["can_interface_is_up"]

    with check:
        assert "lss_state" in state and state["lss_state"] == "Idle"

    with check:
        assert "can_tx_error" in state and isinstance(state["can_tx_error"], bool)


def test_iobus_server_api(shell, strategy, check):
    """
    Test if the LXA IOBus server reports a useful node list.

    Since the testbed does not have an IOBus node connected we can only check, if the server actually reports an
    empty node list.
    """
    r = requests.get(f"http://{strategy.network.address}:8080/nodes/")
    assert r.status_code == 200

    r = json.loads(r.text)

    with check:
        assert "code" in r and r["code"] == 0

    with check:
        assert "error_message" in r and r["error_message"] == ""

    with check:
        assert "result" in r and isinstance(r["result"], list) and not r["result"]


def test_iobus_service_hardening(shell, check):
    """
    Test if the hardening options for the LXA IOBus server have been applied.

    @relation(CYSEC-8, scope=function)
    """

    def _assert_value(property_name: str, should: str) -> None:
        value = shell.run_check(f"systemctl show -p {property_name} --value --no-pager lxa-iobus.service")
        with check:
            assert len(value) == 1  # len(value) == 0 would be an empty result.
            assert value[0] == should

    _assert_value("PrivateDevices", "yes")
    _assert_value("PrivateTmp", "yes")
    _assert_value("ProtectControlGroups", "yes")
    _assert_value("ProtectKernelModules", "yes")
    _assert_value("ProtectKernelTunables", "yes")
    _assert_value("ProtectKernelLogs", "yes")
    _assert_value("ProtectSystem", "strict")
    _assert_value("ReadWritePaths", "/var/cache/lxa-iobus")
