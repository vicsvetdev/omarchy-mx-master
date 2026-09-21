#!/usr/bin/env python3
"""Discovery suite: which endpoint is the mouse, and how we decide.

The Helper's behavioural seam is its conversation with an already-chosen
endpoint, so choosing one is not reachable from there. It is filesystem logic
and is tested as filesystem logic, against a synthetic /sys/class/hidraw built
from the report descriptors the real machine actually publishes.

The four Bolt descriptors below were read off the hardware. Only one of the four
endpoints the receiver exposes carries HID++, and picking the wrong one leaves a
plugin that opens successfully and never hears a thing.
"""

import sys

# Loading the Helper by path must not leave a __pycache__ in the plugin folder:
# the shell restarts the Helper whenever anything under the plugins directory is
# written. Set before the loader runs, and not left to whoever invoked us.
sys.dont_write_bytecode = True

import importlib.machinery  # noqa: E402
import importlib.util  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import Suite  # noqa: E402

# The Helper is an executable without a .py suffix, so it is loaded by path.
HELPER_PATH = os.path.join(os.path.dirname(HERE), "bin", "mx-master-helper")
loader = importlib.machinery.SourceFileLoader("mx_master_helper", HELPER_PATH)
spec = importlib.util.spec_from_loader(loader.name, loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)

# Read from /sys/class/hidraw/hidrawN/device/report_descriptor on the machine
# this plugin was built against.
BOLT_KEYBOARD = bytes.fromhex(
    "05010906a1019508750115002501050719e029e7810281039505050819012905"
    "910295017503910395067508150026ff00050719002aff008100c0"
)
BOLT_MOUSE = bytes.fromhex(
    "05010902a10185020901a1009510750115002501050919012910810295027510"
    "16018026ff7f0501093009318106950175081581257f093881069501050c0a38"
    "028106c0c0050c0901a101850395027510150126ff0219012aff028100c00501"
    "0980a101850495017502150125030982098109838100750115002501099b8106"
    "75058103c005010913a101850b950175011500250109e18106750f8103c0"
)
BOLT_HIDPP = bytes.fromhex(
    "0600ff0901a101851095067508150026ff000901810009019100c00600ff0902"
    "a101851195137508150026ff000902810009029100c0"
)
BOLT_TOUCH = bytes.fromhex(
    "050d0905a10185280922a1029502750115002501094709428102950175062504"
    "09518102750826ff0009308102a4750c26d70a3500469204550e651105010930"
    "810226fa0646f30209318102b4c00922a1029502750115002501094709428102"
    "95017506250409518102750826ff0009308102a4750c26d70a3500469204550e"
    "651105010930810226fa0646f30209318102b4c00922a1029502750115002501"
    "09470942810295017506250409518102750826ff0009308102a4750c26d70a35"
    "00469204550e651105010930810226fa0646f30209318102b4c00922a1029502"
    "75011500250109470942810295017506250409518102750826ff0009308102a4"
    "750c26d70a3500469204550e651105010930810226fa0646f30209318102b4c0"
    "0922a102950275011500250109470942810295017506250409518102750826ff"
    "0009308102a4750c26d70a3500469204550e651105010930810226fa0646f302"
    "09318102b4c0750725050954810275012501050909018102751027ffff000047"
    "ffff0000550c660110050d095681026500550085297508250f0955b102852a96"
    "000126ff000600ff09c5b102c0"
)
RAZER_MIC = bytes.fromhex(
    "050c0901a10185011500250109e909ea75019502814209cd09b509b609b709e2"
    "9505810606ff01090195018106050c090095088106090075089502810606ff07"
    "0901950b81020900950f9102c0050b0905a10185020920150025019501750181"
    "23950175078107c0"
)


def sysfs(entries):
    """Build a /sys/class/hidraw tree. entries: node -> (vendor, product, descriptor)."""
    root = tempfile.mkdtemp(prefix="mx-master-sysfs.")
    for node, (vendor, product, descriptor) in entries.items():
        base = os.path.join(root, node, "device")
        os.makedirs(base)
        with open(os.path.join(base, "uevent"), "w") as fh:
            fh.write(
                f"DRIVER=hid-generic\nHID_ID=0003:{vendor:08X}:{product:08X}\n"
                f"HID_NAME=Whatever\n"
            )
        with open(os.path.join(base, "report_descriptor"), "wb") as fh:
            fh.write(descriptor)
    return root


LOGITECH = 0x046D
BOLT = 0xC548
UNIFYING = 0xC52B
RAZER = 0x1532

suite = Suite("discovery")

# The real machine, as it actually is: the Bolt receiver claims four hidraw
# nodes and exactly one of them speaks HID++.
root = sysfs({
    "hidraw0": (RAZER, 0x0511, RAZER_MIC),
    "hidraw3": (LOGITECH, BOLT, BOLT_KEYBOARD),
    "hidraw4": (LOGITECH, BOLT, BOLT_MOUSE),
    "hidraw5": (LOGITECH, BOLT, BOLT_HIDPP),
    "hidraw6": (LOGITECH, BOLT, BOLT_TOUCH),
})
suite.expect("discovery: the receiver's HID++ endpoint is the one chosen",
             helper.discover(root, "/dev") == "/dev/hidraw5")
shutil.rmtree(root)

# The node number is not stable across a replug or a resume, so it must not be
# what the choice rests on. Same endpoints, different numbers, same answer.
root = sysfs({
    "hidraw11": (LOGITECH, BOLT, BOLT_MOUSE),
    "hidraw12": (LOGITECH, BOLT, BOLT_HIDPP),
    "hidraw13": (LOGITECH, BOLT, BOLT_KEYBOARD),
})
suite.expect("discovery: a replug that renumbers the nodes changes nothing",
             helper.discover(root, "/dev") == "/dev/hidraw12")
shutil.rmtree(root)

# Only the Logi Bolt receiver. The same mouse over another transport, and any
# other Logitech receiver, is not this plugin's device.
root = sysfs({
    "hidraw0": (LOGITECH, UNIFYING, BOLT_HIDPP),
    "hidraw1": (RAZER, 0x0511, BOLT_HIDPP),
})
suite.expect("discovery: a Logitech receiver that is not the Bolt is ignored",
             helper.discover(root, "/dev") is None)
shutil.rmtree(root)

root = sysfs({"hidraw0": (LOGITECH, BOLT, BOLT_MOUSE)})
suite.expect("discovery: a Bolt endpoint without HID++ is not mistaken for one with it",
             helper.discover(root, "/dev") is None)
shutil.rmtree(root)

suite.expect("discovery: nothing plugged in is None, not a guess",
             helper.discover(tempfile.mkdtemp(prefix="mx-master-empty."), "/dev") is None)
suite.expect("discovery: a missing sysfs is None rather than a crash",
             helper.discover("/nonexistent/class/hidraw", "/dev") is None)

# The capability test itself, against each real descriptor.
suite.expect("discovery: the HID++ descriptor carries both the short and long report",
             helper.speaks_hidpp(BOLT_HIDPP))
suite.expect("discovery: the keyboard collection does not",
             not helper.speaks_hidpp(BOLT_KEYBOARD))
suite.expect("discovery: the mouse collection does not",
             not helper.speaks_hidpp(BOLT_MOUSE))
suite.expect("discovery: a vendor page without HID++ report ids does not count",
             not helper.speaks_hidpp(BOLT_TOUCH))

# The DPI list the real device replies with: 200, then steps of 50 up to 8000.
choices = helper.parse_dpi_list(bytes.fromhex("00c8e0321f400000"))
suite.expect("discovery: the device's DPI range is read from the device, not assumed",
             choices[0] == 200 and choices[-1] == 8000 and 1000 in choices
             and choices[1] - choices[0] == 50 and len(choices) == 157)
suite.expect("discovery: an empty DPI list is empty rather than wrong",
             helper.parse_dpi_list(b"\x00\x00") == [])

sys.exit(suite.report())
