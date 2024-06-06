import time

import pytest
import requests


def put_endpoint(fqdn, endpoint, data):
    """PUT data to given endpoint on target."""
    r = requests.put(f"http://{fqdn}/{endpoint}", data=data)
    r.raise_for_status()
    return r


def get_endpoint(fqdn, endpoint):
    """GET given endpoint on target."""
    r = requests.get(f"http://{fqdn}/{endpoint}")
    r.raise_for_status()
    return r


def get_json_endpoint(fqdn, endpoint):
    """GET JSON response from given endpoint on target."""
    return get_endpoint(fqdn, endpoint).json()


def test_tacd_http_temperature(strategy, online):
    """Test tacd temperature endpoint."""
    res = get_json_endpoint(strategy.network.address, "v1/tac/temperatures/soc")

    # TODO: we could check res["ts"] by comparing it to our local time,
    # but that seems prone to false positive errors
    assert 0 < res["value"] < 70


@pytest.mark.parametrize(
    "low, high, endpoint",
    (
        (-0.01, 5.0, "v1/dut/feedback/current"),
        (-5.0, 50.0, "v1/dut/feedback/voltage"),
        (-0.01, 0.7, "v1/usb/host/total/feedback/current"),
        (-0.001, 0.5, "v1/usb/host/port1/feedback/current"),
        (-0.01, 0.5, "v1/usb/host/port2/feedback/current"),
        (-0.001, 0.5, "v1/usb/host/port3/feedback/current"),
        (-5.0, 5.0, "v1/output/out_0/feedback/voltage"),
        (-5.0, 5.0, "v1/output/out_1/feedback/voltage"),
        (-0.01, 0.4, "v1/iobus/feedback/current"),
        (-0.01, 14, "v1/iobus/feedback/voltage"),
    ),
)
def test_tacd_http_adc(strategy, low, high, endpoint):
    """Test tacd ADC endpoints."""
    res = get_json_endpoint(strategy.network.address, endpoint)
    assert low <= res["value"] <= high


def test_tacd_http_locator(strategy, online):
    """Test tacd locator endpoint."""
    endpoint = "v1/tac/display/locator"

    for state in [b"true", b"false"]:
        put_endpoint(strategy.network.address, endpoint, state)
        res = get_endpoint(strategy.network.address, endpoint)
        assert res.content == state


def test_tacd_http_iobus_fault(strategy, online):
    """Test tacd iobus fault endpoint."""
    get_endpoint(strategy.network.address, "v1/iobus/feedback/fault")


@pytest.mark.parametrize(
    "control, states",
    (
        ("v1/dut/powered", (b'"On"', b'"Off"', b'"OffFloating"')),
        ("v1/iobus/powered", (b"true", b"false")),
        ("v1/uart/rx/enabled", (b"true", b"false")),
        ("v1/uart/tx/enabled", (b"true", b"false")),
        ("v1/output/out_0/asserted", (b"true", b"false")),
        ("v1/output/out_1/asserted", (b"true", b"false")),
    ),
)
def test_tacd_http_switch_output(strategy, online, control, states):
    """Test tacd output switching."""
    for state in states:
        put_endpoint(strategy.network.address, control, state)
        time.sleep(0.5)
        res = get_endpoint(strategy.network.address, control)
        assert res.content == state


@pytest.mark.lg_feature("eet")
@pytest.mark.parametrize(
    "endpoint, link, bounds, precondition",
    (
        (
            "v1/output/out_0/feedback/voltage",
            "5V_1K -> -5V -> BUS1 -> OUT0",
            (-5.5, -4.5),
            ("v1/output/out_0/asserted", b"false"),
        ),
        (
            "v1/output/out_0/feedback/voltage",
            "5V_1K -> 5V -> BUS1 -> OUT0",
            (4.5, 5.5),
            ("v1/output/out_0/asserted", b"false"),
        ),
        (
            "v1/output/out_1/feedback/voltage",
            "5V_1K -> -5V -> BUS1 -> OUT1",
            (-5.5, -4.5),
            ("v1/output/out_1/asserted", b"false"),
        ),
        (
            "v1/output/out_1/feedback/voltage",
            "5V_1K -> 5V -> BUS1 -> OUT1",
            (4.5, 5.5),
            ("v1/output/out_1/asserted", b"false"),
        ),
        (
            "v1/output/out_0/feedback/voltage",
            "AUX1 -> BUS1 -> OUT0",
            (3.0, 3.6),
            ("v1/output/out_0/asserted", b"false"),
        ),
        (
            "v1/output/out_1/feedback/voltage",
            "AUX1 -> BUS1 -> OUT1",
            (3.0, 3.6),
            ("v1/output/out_1/asserted", b"false"),
        ),
        (
            "v1/usb/host/port1/feedback/current",
            "USB1_IN -> BUS1 -> CURR -> SHUNT_78R",
            (0.045, 0.065),
            None,
        ),
        (
            "v1/usb/host/port1/feedback/current",
            "USB1_IN -> BUS1 -> CURR -> SHUNT_15R",
            (0.29, 0.33),
            None,
        ),
        (
            "v1/usb/host/port1/feedback/current",
            "USB1_IN -> BUS1 -> CURR -> SHUNT_10R, USB1_IN -> BUS1 -> CURR -> SHUNT_15R",
            (0.46, 0.5),
            None,
        ),
        (
            "v1/usb/host/port2/feedback/current",
            "USB2_IN -> BUS1 -> CURR -> SHUNT_78R",
            (0.045, 0.065),
            None,
        ),
        (
            "v1/usb/host/port2/feedback/current",
            "USB2_IN -> BUS1 -> CURR -> SHUNT_15R",
            (0.29, 0.33),
            None,
        ),
        (
            "v1/usb/host/port2/feedback/current",
            "USB2_IN -> BUS1 -> CURR -> SHUNT_10R, USB2_IN -> BUS1 -> CURR -> SHUNT_15R",
            (0.46, 0.5),
            None,
        ),
        (
            "v1/usb/host/port3/feedback/current",
            "USB3_IN -> BUS1 -> CURR -> SHUNT_78R",
            (0.045, 0.065),
            None,
        ),
        (
            "v1/usb/host/port3/feedback/current",
            "USB3_IN -> BUS1 -> CURR -> SHUNT_15R",
            (0.29, 0.33),
            None,
        ),
        (
            "v1/usb/host/port3/feedback/current",
            "USB3_IN -> BUS1 -> CURR -> SHUNT_10R, USB3_IN -> BUS1 -> CURR -> SHUNT_15R",
            (0.46, 0.5),
            None,
        ),
        (
            "v1/dut/feedback/voltage",
            "AUX3 -> BUS1 -> PWR_IN",
            (11.5, 12.5),
            ("v1/dut/powered", b'"On"'),
        ),
        (
            "v1/dut/feedback/current",
            "AUX3 -> BUS1 -> PWR_IN",
            (-0.05, 0.05),
            ("v1/dut/powered", b'"On"'),
        ),
        (
            "v1/dut/feedback/current",
            "AUX3 -> BUS1 -> PWR_IN, PWR_OUT -> BUS2 -> CURR -> SHUNT_78R",
            (0.14, 0.16),
            ("v1/dut/powered", b'"On"'),
        ),
        (
            "v1/dut/feedback/current",
            "AUX3 -> BUS1 -> PWR_IN, PWR_OUT -> BUS2 -> CURR -> SHUNT_15R",
            (0.70, 0.85),
            ("v1/dut/powered", b'"On"'),
        ),
        (
            "v1/dut/feedback/current",
            "AUX3 -> BUS1 -> PWR_IN, PWR_OUT -> BUS2 -> CURR -> SHUNT_10R",
            (1.1, 1.2),
            ("v1/dut/powered", b'"On"'),
        ),
    ),
)
def test_tacd_eet_analog(strategy, online, endpoint, link, bounds, precondition):
    """Test if analog measurements work with values not equal to zero."""
    if precondition:
        put_endpoint(strategy.network.address, precondition[0], precondition[1])

    strategy.eet.link(link)  # connect supply to output
    time.sleep(0.2)  # give the analog world a moment to settle
    res = get_json_endpoint(strategy.network.address, endpoint)
    assert bounds[0] <= res["value"] <= bounds[1]
