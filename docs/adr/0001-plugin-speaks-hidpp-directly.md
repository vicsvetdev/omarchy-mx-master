---
status: accepted
---

# The plugin speaks HID++ to the mouse directly

Solaar is installed, already manages this mouse, and can do everything the
plugin needs — but reading the battery through it costs 5.0 s per call (1.7 s
through its Python library), its rule engine only runs while its GTK tray app
is running, and its window-condition support is documented as broken under
Wayland. Rather than build a face for Solaar, the plugin opens the Bolt
receiver's hidraw node itself and speaks HID++ directly, which brings the same
battery read down to ~15 ms, removes any runtime dependency on a tray
application, and makes window-aware bindings possible at all.

## Consequences

The plugin reimplements the parts of Solaar it needs, including its
DPI-normalised gesture accumulation and its documented workaround for a
spurious first movement report specific to the MX Master 3S.

Two programs writing the same firmware registers produce silent, confusing
misbehaviour, so the plugin detects a running Solaar and refuses to Arm rather
than competing with it. Because Solaar autostarts on this machine and its saved
configuration diverts the same Gesture Button, disabling that autostart is part
of setting the plugin up — not a workaround.

The kernel is not an alternative here: no driver claims the Bolt receiver
(`046d:C548`) on this system, so there is no `hidpp_battery` power supply and
UPower has nothing to report. Pairing the mouse over Bluetooth instead would
bind `hid-logitech-hidpp` and make the battery available for free; that remains
open, and would make this decision worth revisiting for battery alone.
