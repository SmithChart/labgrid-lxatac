import json
import logging
import sys
import time

import labgrid
from labgrid.logging import StepLogger, basicConfig

"""
Reproducer: Test If The Device has an IPv4 After Boot
=====================================================

This script reproduces a situation where the device is not able to request an
IPv4 address via DHCP.

This script does not flash the device with the firmware to test.
This has to be done outside of this script.
"""

basicConfig(level=logging.CONSOLE)
labgrid.util.helper.processwrapper.enable_logging()
labgrid.consoleloggingreporter.ConsoleLoggingReporter.start(".")
StepLogger.start()
logger = logging.getLogger("main")

labgrid_env = labgrid.Environment("lxatac-vanilla-eet.yaml")
target = labgrid_env.get_target()
strategy = target.get_strategy()
barebox = strategy.barebox
power = strategy.power
shell = strategy.shell

target.activate(power)

retry = 1
while True:
    logger.warning(f"Boot {retry}")
    logger.warning("============")

    power.cycle()
    target.activate(shell)
    logger.warning("Reached userspace")
    strategy.wait_system_ready()

    # wait for ip connectivity given
    # we can not use strategy,wait_online() since that would wait for chrony to sync, which would fail if we hit our
    # problem.
    shell.poll_until_success("ping -c1 _gateway", timeout=60.0)
    logger.warning("System ready")

    # Wait a little longer for good measure
    time.sleep(5)

    # Let's add some metadata to the log (but only once)
    if retry == 1:

        def _log(info):
            for line in info:
                logger.warning(line)

        _log(shell.run_check("cat /etc/os-release"))
        _log(shell.run_check("cat /etc/buildinfo"))

    # Perform the actual check
    [stdout] = shell.run_check("ip -json addr show dev tac-bridge")
    [ip_addr_json] = json.loads(stdout)
    v4_addrs = [
        ai["local"] for ai in ip_addr_json["addr_info"] if ai["family"] == "inet" and "dynamic" in ai and ai["dynamic"]
    ]
    logger.warning("v4 addrs %s", str(v4_addrs))
    if not v4_addrs:
        logger.error("No v4 addrs found")
        logger.error("I've left the device in the problematic state for you to investigate")
        sys.exit(0)

    target.deactivate(shell)

    retry += 1
