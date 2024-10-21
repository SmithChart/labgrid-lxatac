import logging

import labgrid
from labgrid.logging import StepLogger, basicConfig

"""
Reproducer: Reboot until the reset reason is iwdg2
==================================================

FIXME
"""

basicConfig(level=logging.CONSOLE, format='%(asctime)s %(levelname)-7.7s %(name)15.15s: %(message)s')
labgrid.util.helper.processwrapper.enable_logging()
labgrid.consoleloggingreporter.ConsoleLoggingReporter.start(".")
StepLogger.start()
logger = logging.getLogger("main")

labgrid_env = labgrid.Environment("lxatac-vanilla-eet.yaml")
target = labgrid_env.get_target()
strategy = target.get_strategy()
barebox = strategy.barebox
shell = strategy.shell
console = strategy.console
power = strategy.power

strategy.status = 1
logger.info(f"Initial Boot with bootstrapping")
strategy.transition("barebox")
logger.info("Reached barebox. Setting up bootchooser")
strategy.barebox.run_check(f"state.bootstate.system0.priority=20")
strategy.barebox.run_check(f"state.bootstate.system0.remaining_attempts=3")
strategy.barebox.run_check("state -s")
logger.info("Transitioning to shell")
strategy.transition("shell")

retry = 1
while True:
    logger.info("==================================")
    logger.info(f"Round {retry}")
    logger.info("==================================")
    target.deactivate(strategy.barebox)
    target.deactivate(strategy.fastboot)
    target.deactivate(shell)
    target.deactivate(console)
    target.activate(power)
    logger.info("Powering off")
    power.off()

    target.activate(console)
    logger.info("Powering on")
    power.on()

    console.expect(["rst_por"])
    logger.info("Saw power on reset. Awaiting the rest of the boot.")
    
    res = console.expect(["rst_iwdg2", "lxatac-00034 login:", ], timeout=120)
    if res == 0:
        logger.info(f"🧨🧨🧨🧨🧨💥💥💥💥💥 WATCHDOG RESET after {retry} loops")
        exit(0)
    else:
        logger.info("normal boot")

    logger.info("Resetting bootchooser remaining attempts")
    power.off()
    strategy.status = 1
    strategy.transition("barebox")
    logger.info("Reached barebox. Setting up bootchooser")
    strategy.barebox.run_check(f"state.bootstate.system0.priority=20")
    strategy.barebox.run_check(f"state.bootstate.system0.remaining_attempts=3")
    strategy.barebox.run_check("state -s")

    retry += 1
