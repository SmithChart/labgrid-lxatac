import time

import pytest


@pytest.mark.lg_feature("eet")
def test_interface_usb_io(strategy, shell):
    """Test USB device by writing a small file onto the device and reading it again"""
    usbpath = shell.target.env.config.get_target_option(shell.target.name, "usbpath")

    # Connect USB-Stick to DUT
    strategy.eet.link("USB1_IN -> USB1_OUT")

    # Create tmp file
    shell.run_check("dd if=/dev/random of=/tmp/test_file bs=1M count=15")
    checksum1 = shell.run_check("md5sum /tmp/test_file")
    assert len(checksum1) > 0

    # Get usb device file
    usb_device = shell.run_check(f"grep -rs '^DEVNAME=' /sys/bus/usb/devices/{usbpath} | cut -d= -f2 | grep sd[a-z]$")
    assert len(usb_device) > 0

    # Write tmp file onto usb device
    stdout, stderr, returncode = shell.run(f"dd if=/tmp/test_file of=/dev/{usb_device} bs=1M count=15")
    assert returncode == 0
    assert len(stdout) > 0
    assert len(stderr) == 0, f"could not write onto '{usb_device}': {stderr}"

    # Disconnect and connect the USB stick to make sure all buffers have been flushed.
    strategy.eet.link("")
    time.sleep(1)
    strategy.eet.link("USB1_IN -> USB1_OUT")
    time.sleep(5)

    # Get usb device file
    usb_device = shell.run_check(f"grep -rs '^DEVNAME=' /sys/bus/usb/devices/{usbpath} | cut -d= -f2 | grep sd[a-z]$")
    assert len(usb_device) > 0

    # Read tmp file from usb device
    stdout, stderr, returncode = shell.run(f"dd if=/dev/{usb_device} of=/tmp/test_file bs=1M count=15")
    assert returncode == 0
    assert len(stdout) > 0
    assert len(stderr) == 0, f"could not read read '{usb_device}': {stderr}"

    # Compare checksums
    checksum2 = shell.run_check("md5sum /tmp/test_file")
    assert len(checksum2) > 0
    assert checksum1 == checksum2, f"checksum are different: {checksum1} != {checksum2}"
