import pytest
import yaml


def run_stressor(shell, args):
    output = shell.run_check(f"stress-ng --yaml /tmp/stress-ng.yaml --timeout 10s --metrics {args}")
    print(output)
    data = shell.run_check("cat /tmp/stress-ng.yaml")
    data = yaml.load("\n".join(data), Loader=yaml.SafeLoader)
    return data


@pytest.fixture()
def services_stopped(shell):
    shell.run_check("systemctl stop tacd")
    shell.run_check("systemctl stop lxa-iobus")
    shell.run_check("systemctl stop labgrid-exporter")
    yield
    shell.run_check("systemctl start tacd")
    shell.run_check("systemctl start lxa-iobus")
    shell.run_check("systemctl start labgrid-exporter")


# run multiple similar tests
@pytest.mark.parametrize(
    "stressor",
    (
        "matrix",
        "zero",
        "yield",
        "switch",
        "shm",
        "remap",
        "qsort",
        "bsearch",
        "atomic",
    ),
)
def test_stress(shell, stressor, record_property, services_stopped):
    args = "--shm-bytes 1M" if stressor == "shm" else ""

    data = run_stressor(shell, f"--{stressor} 0 {args}")
    metrics = data["metrics"][0]
    assert metrics["stressor"] == stressor

    record_property("bogo-ops-per-second-usr-sys-time", metrics["bogo-ops-per-second-usr-sys-time"])
