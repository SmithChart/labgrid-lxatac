import enum

import attr
from labgrid import step, target_factory
from labgrid.driver import ExecutionError
from labgrid.strategy import Strategy, StrategyError

# Possible state transitions:
#
#            +---------------------------------------------------------+
#            v                                                         |
#            +--------+------------+----------+  +---------------------+
#            v        v            v          |  v                     |
# unknown -> off -1-> bootstrap -> barebox -> shell -> network --------+
#
# 1) Via bootstrap() but only once


class Status(enum.Enum):
    unknown = 0
    off = 1
    bootstrap = 2
    barebox = 3
    shell = 4
    network = 5


@target_factory.reg_driver
@attr.s(eq=False)
class LXATACStrategy(Strategy):
    """
    LXATACStrategy - Strategy to bootstrap the LAG LXATAC's rootfs and switch to barebox and shell.
    """

    bindings = {
        "dfu_mode": "DigitalOutputProtocol",
        "httpprovider": "HTTPProviderDriver",
        "power": "PowerProtocol",
        "console": "ConsoleProtocol",
        "dfu": "DFUDriver",
        "fastboot": "AndroidFastbootDriver",
        "barebox": "BareboxDriver",
        "shell": "ShellDriver",
        "network": "NetworkService",
        "eet": {"LxatacEETDriver", None},
        "ethmux": {"LXAIOBusPIODriver", None},
    }

    status = attr.ib(default=Status.unknown)
    mmc_bootstrapped = attr.ib(default=False)

    @property
    def target_hostname(self):
        fqdn = self.network.address
        hostname = fqdn.split(".", maxsplit=1)[0] if "." in fqdn else fqdn
        return hostname

    def bootstrap(self):
        self.transition(Status.off)

        self.dfu_mode.set(True)
        self.power.cycle()

        self.target.activate(self.dfu)

        # download tf-a to "FSBL"
        tfa_img = self.target.env.config.get_image_path("tfa")
        self.dfu.download(1, tfa_img)

        # download emmc-boot-image to "Partition3"
        mmc_boot_fip_img = self.target.env.config.get_image_path("mmc_boot_fip")
        self.dfu.download(3, mmc_boot_fip_img)
        self.dfu.detach(0)

        self.target.deactivate(self.dfu)

        self.target.activate(self.barebox)
        self.target.activate(self.fastboot)

        # write eMMC user partition
        mmc_img = self.target.env.config.get_image_path("mmc")
        self.fastboot.flash("mmc", mmc_img)

        # write eMMC boot partition
        mmc_boot_img = self.target.env.config.get_image_path("mmc_boot")
        self.fastboot.flash("bbu-mmc", mmc_boot_img)

        self.target.deactivate(self.fastboot)
        self.target.deactivate(self.barebox)

        self.dfu_mode.set(False)

        self.mmc_bootstrapped = True

    def wait_online(self):
        self.shell.poll_until_success("ping -c1 _gateway", timeout=60.0)

        # Also make sure we have accurate time, so that TLS works.
        self.shell.run_check("chronyc waitsync", timeout=120.0)

    def wait_system_ready(self):
        try:
            self.shell.run("systemctl is-system-running --wait", timeout=90)
        except ExecutionError:
            # gather information about failed units
            self.shell.run("systemctl list-units --failed --no-legend --plain --no-pager")
            raise

    @step(args=["status"])
    def transition(self, status, *, step):
        if not isinstance(status, Status):
            status = Status[status]

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")

        elif status == self.status:
            step.skip("nothing to do")
            return

        elif status == Status.off:
            if self.status in [Status.shell, Status.network]:
                # Cleanly shut down the labgrid exporter to help the
                # coordinator clean up stale resources.
                self.shell.run("systemctl stop labgrid-exporter", timeout=90)

            self.target.deactivate(self.barebox)
            self.target.deactivate(self.shell)
            self.target.deactivate(self.fastboot)

            self.target.activate(self.power)
            self.power.off()

            # assure the board is not jumpered for dfu mode
            self.target.activate(self.dfu_mode)
            self.dfu_mode.set(False)

            self.target.activate(self.console)

            self.activate_optionals()

        elif status == Status.bootstrap:
            self.transition(Status.off)

            if not self.mmc_bootstrapped:
                self.bootstrap()

        elif status == Status.barebox:
            self.transition(Status.bootstrap)

            # cycle power
            self.power.cycle()
            # interrupt barebox
            self.target.activate(self.barebox)
            self.barebox.run_check("global linux.bootargs.loglevel=loglevel=6")

        elif status == Status.shell:
            # No need to reboot just because we checked for network connectivity.
            if self.status not in [Status.network]:
                # transition to barebox
                self.transition(Status.barebox)

                self.barebox.boot("")
                self.barebox.await_boot()

                self.target.activate(self.shell)
            self.wait_system_ready()

        elif status == Status.network:
            self.transition(Status.shell)
            self.wait_online()

        else:
            raise StrategyError(f"no transition found from {self.status} to {status}")

        self.status = status

    @step(args=["status"])
    def force(self, status):
        if not isinstance(status, Status):
            status = Status[status]

        self.target.activate(self.power)
        self.target.activate(self.console)
        self.activate_optionals()

        if status == Status.barebox:
            self.target.activate(self.barebox)
        elif status == Status.shell:
            self.target.activate(self.shell)
        elif status == Status.bootstrap:
            pass
        else:
            raise StrategyError(f"can not force state {status}")

        self.mmc_bootstrapped = True
        self.status = status

    def activate_optionals(self):
        if self.eet:
            self.target.activate(self.eet)
        if self.ethmux:
            self.target.activate(self.ethmux)
            self.ethmux.set(True)  # Connect upstream Ethernet to Lab network as default
