#!/usr/bin/env python3
"""Behavioural suite for the Helper, driven entirely through its one seam.

Every test here feeds the Helper bytes, settings and time, and asserts on what
the Helper shows the world: the state it publishes, the frames it wrote to the
device, and which external tools it invoked with which arguments. Nothing
reaches inside it — an assertion about an internal flag pins an implementation
rather than a behaviour, and has to be rewritten the first time the
implementation improves.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import Helper, Suite  # noqa: E402

suite = Suite("helper")

# A movement unit is 1/15 inch whatever the DPI, and the Tap/Direction threshold
# is 2.0 units. At 1000 DPI that is about 134 sensor counts.
UNIT_AT_1000 = 1000 / 15.0


def flick(helper, dx, dy):
    """A complete Gesture: down, the bogus first report, one stroke, up."""
    helper.device.press_gesture()
    helper.device.move(3, 3)          # the report the MX Master 3S always lies about
    helper.device.move(dx, dy)
    helper.device.release_gesture()


def tap(helper):
    helper.device.press_gesture()
    helper.device.release_gesture()


# ------------------------------------------------------------ 02 — battery

h = Helper()
state = h.wait_for(present=True)
suite.expect("battery: the percentage the device reports is published",
             state is not None and state["battery"] == 90 and state["present"] is True)
suite.expect("battery: the mouse's own DPI is published with it",
             state is not None and state["dpi"] == 1000)
# The published shape is the contract the widget is a projection of. A field
# that quietly appears or disappears is a widget rendering undefined.
suite.expect("battery: the published state is exactly the agreed shape",
             state is not None and sorted(state) == sorted([
                 "present", "battery", "charging", "dpi", "dpiMin", "dpiMax",
                 "dpiStep", "armed", "status", "reason", "bindings"]))
suite.expect("battery: the Bindings in force are published, so the panel can show them",
             state is not None and sorted(state["bindings"]) == sorted(
                 ["tap", "up", "down", "left", "right"])
             and state["bindings"]["tap"]["action"]["keys"] == ["ctrl", "w"]
             and state["bindings"]["left"] is None)
suite.expect("battery: the window-match field is in the stored shape, and empty",
             state is not None and state["bindings"]["tap"]["window"] == "")
h.stop()

h = Helper()
h.wait_for(present=True)
h.device.broadcast_battery(64)
state = h.wait(lambda s: s.get("battery") == 64)
suite.expect("battery: a broadcast from the mouse updates the percentage",
             state is not None)
h.device.broadcast_battery(64, status=1)
state = h.wait(lambda s: s.get("charging") is True)
suite.expect("battery: charging is published when the cable goes in", state is not None)
h.stop()

h = Helper()
h.wait_for(present=True)
h.device.disconnect()
state = h.wait_for(present=False)
suite.expect("battery: the widget is hidden entirely when the mouse goes away",
             state is not None and state["battery"] is None and state["status"] == "offline")
suite.expect("battery: being away comes with a reason, not just bad news",
             state is not None and bool(state["reason"]))
h.stop()

# A mouse that is asleep before the Helper ever starts must not be presented.
h = Helper()
h.device.online = False
h.device.disconnect()
state = h.wait_for(present=False)
suite.expect("battery: a mouse that was already asleep is never shown as present",
             state is not None)
h.stop()


# ----------------------------------------- 03 — disconnect, sleep, reload

h = Helper(settings={"dpi": 1000})
h.wait_for(present=True)
h.device.disconnect()
h.wait_for(present=False)
h.device.connect()
state = h.wait_for(present=True)
suite.expect("recovery: the mouse coming back brings the widget back by itself",
             state is not None and state["battery"] == 90)
h.stop()

h = Helper(settings={"dpi": 2000})
h.wait_for(armed=True)
before = len(h.device.arming_writes())
h.device.power_cycle()
h.wait(lambda s: s.get("armed") is True, timeout=5)
h.settle(0.2)
suite.expect("recovery: a power cycle re-arms the Gesture Button",
             len(h.device.arming_writes()) > before
             and (h.device.diversion_flags & 0x11) == 0x11)
suite.expect("recovery: a power cycle puts the chosen DPI back", h.device.dpi == 2000)
h.stop()

# State can drift without any notification arriving — the tick is what notices.
h = Helper()
h.wait_for(armed=True)
h.device.diversion_flags = 0x00
h.tick()
h.settle(0.3)
suite.expect("recovery: the verify tick repairs Diversion that drifted",
             (h.device.diversion_flags & 0x11) == 0x11)
h.stop()

first = Helper()
first.wait_for(present=True)
second = Helper(extra_env={"MX_MASTER_LOCK": first.env["MX_MASTER_LOCK"]})
second.settle(0.6)
waiting = second.state is None
first.stop()
came_up = second.wait(lambda s: s.get("present") is True, timeout=6) is not None
suite.expect("recovery: a second Helper waits for its predecessor rather than racing it",
             waiting and came_up)
second.stop()


# ------------------------------------------------------ 04 — battery alerts

h = Helper(settings={"lowBattery": 20, "criticalBattery": 10})
h.wait_for(present=True)
h.device.broadcast_battery(50)
h.wait(lambda s: s.get("battery") == 50)
h.device.broadcast_battery(18)
calls = h.wait_for_call("omarchy-notification-send", 1)
suite.expect("alerts: crossing the low threshold notifies exactly once", len(calls) == 1)
suite.expect("alerts: the notification is sent the way Omarchy sends notifications",
             bool(calls) and "-g" in calls[0] and "-u" in calls[0]
             and calls[0][calls[0].index("-u") + 1] == "normal")

for level in (17, 16, 15, 14):
    h.device.broadcast_battery(level)
    h.tick()
h.settle(0.3)
suite.expect("alerts: staying below the threshold does not repeat the notification",
             len(h.calls("omarchy-notification-send")) == 1)

h.device.broadcast_battery(9)
calls = h.wait_for_call("omarchy-notification-send", 2)
suite.expect("alerts: crossing the critical threshold notifies once more", len(calls) == 2)
suite.expect("alerts: the critical notification is the urgent one",
             len(calls) == 2 and calls[1][calls[1].index("-u") + 1] == "critical")

for level in (8, 7, 6):
    h.device.broadcast_battery(level)
h.settle(0.3)
suite.expect("alerts: below critical stays quiet too",
             len(h.calls("omarchy-notification-send")) == 2)

h.device.broadcast_battery(80, status=1)
h.settle(0.2)
h.device.broadcast_battery(18)
calls = h.wait_for_call("omarchy-notification-send", 3)
suite.expect("alerts: charging back up re-arms the warning for the next discharge",
             len(calls) == 3)
h.stop()

# A session that starts on an already-flat mouse crossed the threshold while
# nobody was watching. Saying so once is the whole point; saying it again on
# every hot-reload of the shell is what the remembered edges prevent.
shared_state = os.path.join(tempfile.mkdtemp(prefix="mx-master-edges."), "warned.json")
h = Helper(settings={"lowBattery": 20, "criticalBattery": 10},
           extra_env={"MX_MASTER_STATE": shared_state})
h.device.battery = 8
h.wait_for(present=True)
calls = h.wait_for_call("omarchy-notification-send", 1)
suite.expect("alerts: a session that starts on a flat mouse is told, once",
             len(calls) == 1 and calls[0][calls[0].index("-u") + 1] == "critical")
h.stop()

again = Helper(settings={"lowBattery": 20, "criticalBattery": 10},
               extra_env={"MX_MASTER_STATE": shared_state})
again.device.battery = 8
again.wait_for(present=True)
again.settle(0.4)
suite.expect("alerts: a Helper restart does not say it a second time",
             again.calls("omarchy-notification-send") == [])
again.stop()
shutil.rmtree(os.path.dirname(shared_state), ignore_errors=True)


# ---------------------------------------------------------------- 05 — DPI

h = Helper()
h.wait_for(present=True)
for value in range(1000, 1500, 50):      # a drag, as the slider emits it
    h.settings({"dpi": value})
h.settle(0.5)
writes = h.device.dpi_writes()
suite.expect("dpi: a full drag produces one device write, not one per step",
             len(writes) == 1 and writes[0] == 1450)
h.stop()

h = Helper()
h.wait_for(present=True)
h.settings({"dpi": 1234})
h.settle(0.4)
suite.expect("dpi: a value the mouse does not accept is snapped to one it does",
             h.device.dpi_writes() == [1250])
h.stop()

h = Helper()
h.wait_for(present=True)
h.settings({"dpi": 99999})
h.settle(0.4)
suite.expect("dpi: a value past the end of the range is clamped to it",
             h.device.dpi_writes() == [8000])
h.stop()

h = Helper(settings={"dpi": 3000})
h.wait(lambda s: s.get("dpi") == 3000)
h.device.power_cycle()
h.wait_for(present=False)
h.wait_for(present=True)
h.settle(0.3)
suite.expect("dpi: the chosen value is put back after the mouse power-cycles",
             h.device.dpi == 3000 and h.state["dpi"] == 3000)
h.stop()


# ------------------------------------------------- 06 — arming and conflict

h = Helper()
state = h.wait_for(armed=True)
suite.expect("arming: the Gesture Button is armed when the mouse connects",
             state is not None and state["status"] == "armed"
             and (h.device.diversion_flags & 0x11) == 0x11)
suite.expect("arming: an armed plugin has nothing to explain",
             state is not None and state["reason"] is None)

writes_before = len(h.device.arming_writes())
h.tick()
h.tick()
h.settle(0.3)
suite.expect("arming: repeating it changes nothing and errors nothing",
             h.state["armed"] is True and (h.device.diversion_flags & 0x11) == 0x11)
suite.expect("arming: a tick on an already-armed mouse writes nothing to it",
             len(h.device.arming_writes()) == writes_before)
h.stop()

h = Helper(conflict=True)
state = h.wait_for(status="conflict")
suite.expect("conflict: a running device manager is detected and the plugin does not arm",
             state is not None and state["armed"] is False)
suite.expect("conflict: the reason is actionable rather than just bad news",
             state is not None and "Solaar" in (state["reason"] or ""))
h.settings({"dpi": 3000})
h.tick()
h.settle(0.4)
suite.expect("conflict: while it exists the plugin writes no device configuration at all",
             h.device.arming_writes() == [] and h.device.dpi_writes() == [])
suite.expect("conflict: it is recorded in the log rather than only on screen",
             any("conflict" in line.lower() for line in h.stderr))

h.command("resolveConflict")
state = h.wait_for(armed=True)
suite.expect("conflict: one action resolves it and gestures arm with no shell restart",
             state is not None and state["status"] == "armed")
suite.expect("conflict: resolving it stops the running instance",
             len(h.calls("pkill")) >= 1)
with open(h.autostart) as fh:
    desktop = fh.read()
suite.expect("conflict: resolving it disables the autostart entry",
             "X-GNOME-Autostart-enabled=false" in desktop and "Hidden=true" in desktop)
suite.expect("conflict: the other program's own configuration is left untouched",
             "Exec=solaar --window=hide" in desktop and "Name=Solaar" in desktop)
h.stop()

# The conflict ending on its own must arm on the next tick, with no restart.
# Diverting the Gesture Button removes its ordinary function. Taking it when no
# Action could be delivered is strictly worse than leaving it alone, and a panel
# saying "armed" while every Tap does nothing is the silent failure the status
# line exists to prevent.
h = Helper(missing_tools=("wtype",))
state = h.wait(lambda s: s.get("present") is True and s.get("armed") is False)
suite.expect("arming: the Gesture Button is not taken when keystrokes cannot be delivered",
             state is not None and "wtype" in (state["reason"] or ""))
suite.expect("arming: and the mouse's configuration is left alone while that is true",
             h.device.arming_writes() == [])
h.stop()

h = Helper(conflict=True)
h.wait_for(status="conflict")
h.end_conflict()
h.tick()
state = h.wait_for(armed=True)
suite.expect("conflict: once it is gone, gestures arm by themselves", state is not None)
h.stop()


# ------------------------------------------------------- 07 — tap closes a tab

h = Helper()
h.wait_for(armed=True)
tap(h)
calls = h.wait_for_call("wtype", 1)
suite.expect("tap: a press-to-release with no movement closes the tab",
             calls == [["-M", "ctrl", "-k", "w", "-m", "ctrl"]])
suite.expect("tap: the keystroke goes through the virtual-keyboard path",
             len(h.calls("wtype")) == 1 and h.calls("ydotool") == [])
h.settle(0.2)
suite.expect("tap: it fires once per press-to-release, never twice",
             len(h.calls("wtype")) == 1)
tap(h)
calls = h.wait_for_call("wtype", 2)
suite.expect("tap: a second Tap fires a second time", len(calls) == 2)
h.stop()


# --------------------------------------------- 08 — directions and the recogniser

h = Helper()
h.wait_for(armed=True)
flick(h, 0, -300)
calls = h.wait_for_call("wtype", 1)
suite.expect("direction: holding and moving up reopens the last closed tab",
             calls == [["-M", "ctrl", "-M", "shift", "-k", "t", "-m", "shift", "-m", "ctrl"]])
h.stop()

h = Helper()
h.wait_for(armed=True)
flick(h, -120, -300)      # a roughly-upward flick, well off the axis
calls = h.wait_for_call("wtype", 1)
suite.expect("direction: a roughly-upward flick is still up — quadrants, not narrow bands",
             len(calls) == 1 and "t" in calls[0])
h.stop()

h = Helper()
h.wait_for(armed=True)
h.device.press_gesture()
h.device.move(0, -300)    # the only movement, and it is the discarded one
h.device.release_gesture()
calls = h.wait_for_call("wtype", 1)
suite.expect("direction: the first movement report after button-down is discarded",
             calls == [["-M", "ctrl", "-k", "w", "-m", "ctrl"]])
h.stop()

h = Helper()
h.wait_for(armed=True)
flick(h, 0, -100)         # 1.5 units at 1000 DPI — under the threshold
calls = h.wait_for_call("wtype", 1)
suite.expect("direction: movement under the threshold is a Tap",
             calls == [["-M", "ctrl", "-k", "w", "-m", "ctrl"]])
h.stop()

h = Helper()
h.wait_for(armed=True)
flick(h, 0, -150)         # 2.25 units — just over it, and so a Direction
calls = h.wait_for_call("wtype", 1)
suite.expect("direction: movement just over the threshold is a Direction, not a Tap",
             len(calls) == 1 and "t" in calls[0])
h.stop()

# Down, Left and Right are unbound: no keystroke, no notification, no feedback.
for name, (dx, dy) in {"down": (0, 300), "left": (-300, 0), "right": (300, 0)}.items():
    h = Helper()
    h.wait_for(armed=True)
    flick(h, dx, dy)
    h.settle(0.3)
    suite.expect(f"direction: an unbound {name} produces no effect of any kind",
                 h.calls("wtype") == [] and h.calls("omarchy-notification-send") == [])
    h.stop()

# The same physical stroke at twice the DPI is twice the sensor counts, and must
# still be the same Gesture.
h = Helper(settings={"dpi": 2000})
h.wait(lambda s: s.get("dpi") == 2000)
flick(h, 0, -300)         # 2.25 units at 2000 DPI
calls = h.wait_for_call("wtype", 1)
suite.expect("direction: movement is normalised against DPI, so a flick feels the same",
             len(calls) == 1 and "t" in calls[0])
h.stop()

h = Helper(settings={"dpi": 2000})
h.wait(lambda s: s.get("dpi") == 2000)
flick(h, 0, -150)         # half the distance at 2000 DPI — under the threshold
calls = h.wait_for_call("wtype", 1)
suite.expect("direction: half that stroke at the same DPI is a Tap",
             calls == [["-M", "ctrl", "-k", "w", "-m", "ctrl"]])
h.stop()

# Stillness splits a held Gesture into Segments; the first one resolves it.
h = Helper()
h.wait_for(armed=True)
h.device.press_gesture()
h.device.move(3, 3)
h.device.move(0, -300)
h.settle(0.3)             # the hand goes still — that ends the Segment
h.device.move(300, 0)
h.device.release_gesture()
calls = h.wait_for_call("wtype", 1)
suite.expect("direction: stillness splits a held Gesture, and the first Segment resolves it",
             len(calls) == 1 and "t" in calls[0])
h.stop()

# A Gesture while the mouse is not armed is not the plugin's to act on.
h = Helper(conflict=True)
h.wait_for(status="conflict")
flick(h, 0, -300)
h.settle(0.3)
suite.expect("direction: nothing fires while another program holds the mouse",
             h.calls("wtype") == [])
h.stop()


# ----------------------------------------------------------- 09 — binding editor

h = Helper()
h.wait_for(armed=True)
pid = h.proc.pid
arming_before = len(h.device.arming_writes())
h.settings({"bindings": {
    "tap": {"window": "", "action": {"type": "keystroke", "keys": ["ctrl", "w"]}},
    "up": {"window": "", "action": {"type": "keystroke", "keys": ["ctrl", "shift", "t"]}},
    "down": {"window": "", "action": {"type": "keystroke", "keys": ["super", "k"]}},
    "left": None,
    "right": None,
}})
h.settle(0.2)
flick(h, 0, 300)
calls = h.wait_for_call("wtype", 1)
# Stored as "super", which is what anyone hand-editing shell.json would write;
# wtype only answers to "logo", and a Binding that names the key its owner knows
# must not silently do nothing.
suite.expect("bindings: a changed Binding takes effect on the next Gesture",
             calls == [["-M", "logo", "-k", "k", "-m", "logo"]])
suite.expect("bindings: changing one does not restart the Helper",
             h.proc.pid == pid and h.proc.poll() is None)
suite.expect("bindings: changing one does not disturb the mouse",
             len(h.device.arming_writes()) == arming_before)

h.settings({"bindings": {"tap": None, "up": None, "down": None, "left": None, "right": None}})
h.settle(0.2)
tap(h)
h.settle(0.3)
suite.expect("bindings: a Binding can be removed, and then the Gesture does nothing",
             len(h.calls("wtype")) == 1)
h.stop()

# Run by hand in a terminal, without configuring anything.
h = Helper(args=("--once",))
h.proc.wait(timeout=10)
suite.expect("debugging: --once prints one state line and exits",
             len(h.states) == 1 and h.states[0]["battery"] == 90
             and h.proc.returncode == 0)
suite.expect("debugging: --once leaves the mouse's configuration alone",
             h.device.arming_writes() == [] and h.device.dpi_writes() == [])
h.stop()


sys.exit(suite.report())
