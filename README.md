# MX Master

An Omarchy shell plugin that reads the battery, sets the DPI, and turns thumb
gestures into keystrokes for a Logitech MX Master 3S — by speaking HID++ to the
mouse directly rather than through any other device manager.

- The bar shows the mouse's battery, and disappears entirely when the mouse is
  asleep or gone.
- Left click opens a panel with a DPI slider, the five gesture Bindings, and a
  line saying whether gestures are armed and why not if they are not.
- Right click hides or shows the percentage, and remembers the choice.
- Tapping the Gesture Button closes the current browser tab. Holding it and
  flicking the mouse up reopens the last closed one.
- One notification when the battery gets low, and one more when it gets
  critical — not one a minute.

## Installing

```bash
omarchy plugin add https://github.com/vicsvetdev/omarchy-mx-master.git --enable
```

That clones the repo, checks the manifest, puts it in
`~/.config/omarchy/plugins/vicsvetdev.mx-master/` and adds the widget to the right
of your bar. Drop `--enable` to review the code first and turn it on later with
`omarchy plugin enable vicsvetdev.mx-master`; add `--yes` to skip every prompt,
which is the path for scripts.

> Plugins run as unsandboxed code inside your long-lived `omarchy-shell`
> process. That is true of this one too — read it before you enable it.

Afterwards:

```bash
omarchy plugin update vicsvetdev.mx-master   # fast-forward to the latest
omarchy plugin remove vicsvetdev.mx-master   # and it is gone
```

### What it needs

- **An MX Master 3S on a Logi Bolt receiver.** The same mouse over USB-C or
  Bluetooth is a different endpoint and is not this plugin's device, and no
  other Logitech device is either.
- **`wtype`**, for delivering keystrokes through the Wayland virtual-keyboard
  protocol.
- **`omarchy-notification-send`**, for the low-battery notices.

Both ship with Omarchy — `wtype` is in its base packages and
`omarchy-notification-send` is part of Omarchy itself — so on a stock system
there is nothing to install. `omarchy plugin add` only clones and validates;
it installs no packages and runs no hooks, so if `wtype` has been removed,
`sudo pacman -S wtype` puts it back. Until it is there the plugin will not take
the Gesture Button at all, and the panel says why rather than pretending
gestures work.

### One thing needs root, once

`/dev/hidraw*` is root-only by default, so the plugin cannot open the receiver
until a udev rule says the seated user may. The rule ships with the plugin;
`omarchy plugin add` clones files and nothing else, so install it by hand:

```bash
sudo cp udev/99-mx-master.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Then unplug the receiver and plug it back in. Until that is done the widget
stays hidden and the panel says it has no permission, naming this rule.

If you already run Solaar, its own rule covers this — which is worth knowing,
because it means a machine with Solaar installed appears to work without the
step above and a machine without it does not. Solaar's rule grants raw access
to *every* Logitech device; the one here is scoped to the Bolt receiver
(`046d:c548`) alone, since raw access to a receiver permits firmware updates.

Nothing else needs root, there is no build step and nothing to compile: the
Helper is Python using only the standard library, and the virtual-keyboard
path needs no special permission.

> **If the widget does not appear, restart the shell once** with
> `omarchy-restart-shell`. Qt's QML engine caches what it found in a directory,
> so an entry point that shows up after the shell has already looked for it
> stays invisible, and the log reports `No such file or directory` for a file
> that is plainly there. Installing from git usually dodges this, because the
> directory is new to the engine; it reliably bites while developing in place.

### Installing by hand

Without git, copy the folder to `~/.config/omarchy/plugins/vicsvetdev.mx-master/`
— the directory has to be named after the manifest id — then:

```bash
omarchy-shell shell rescanPlugins
omarchy plugin enable vicsvetdev.mx-master
```

Removing the folder removes the plugin.

### Solaar

Solaar can do everything this plugin does, and if it is running it is managing
the same mouse. Two programs writing the same firmware registers produce
behaviour neither can explain, so the plugin detects Solaar and stands down —
it will not Arm, it writes no device configuration, and the panel says so.

The panel offers one action that resolves it: it turns off Solaar's autostart
entry and stops the running instance. It never touches Solaar's own
configuration, partly as manners and partly because Solaar rewrites that file
on exit and would clobber any edit. To go back to Solaar, set
`X-GNOME-Autostart-enabled=true` in `~/.config/autostart/solaar.desktop` and
drop the `Hidden=true` line.

## Settings

Settings live in `~/.config/omarchy/shell.json`, inline on this plugin's bar
entry, alongside everything else in the shell. Nothing is stored inside the
plugin folder — saving a file there trips the shell's plugin hot-reload, which
would restart the Helper every time a setting changed.

The scalar settings (`showPercent`, `dpi`, `lowBattery`, `criticalBattery`)
appear in the ordinary Omarchy settings UI. Bindings are edited in the plugin's
own panel, because the manifest schema only carries scalars.

A Binding is stored as a tagged Action so other kinds of Action can arrive later
as new variants. The `window` field is there so that gating a Binding on the
focused window can return without reshaping stored configuration; it is empty
and nothing consults it yet.

```json
{
  "id": "vicsvetdev.mx-master",
  "dpi": 1000,
  "lowBattery": 20,
  "criticalBattery": 10,
  "showPercent": true,
  "bindings": {
    "tap":   { "window": "", "action": { "type": "keystroke", "keys": ["ctrl", "w"] } },
    "up":    { "window": "", "action": { "type": "keystroke", "keys": ["ctrl", "shift", "t"] } },
    "down":  null,
    "left":  null,
    "right": null
  }
}
```

Modifier names are the ones `wtype` answers to — `ctrl`, `shift`, `alt`, `logo`,
`altgr`. `super`, `meta` and `cmd` are accepted and translated, because those
are what people write.

## How it is put together

A **Service**, a **Helper**, and a bar widget with a panel.

The **Helper** (`bin/mx-master-helper`) is the only thing that talks to the
mouse. It holds the receiver's HID++ endpoint open and owns every decision:
Arming, Conflict detection, Gesture recognition, Binding lookup and Action
dispatch, battery state and its notification edges, and DPI. It publishes one
state object on standard output and takes settings on standard input. It reads
no configuration file and watches none, so changing a Binding does not restart
it and does not disturb the mouse.

The **Service** (`Service.qml`) owns the Helper's lifetime and nothing else. It
is mounted once per shell session, which is what keeps one Helper holding the
device even though the bar is built once per monitor.

The **widget and panel** (`Panel.qml`) are a pure projection of the state the
Helper publishes. They render; they do not decide. That is load-bearing rather
than stylistic — it is what keeps the whole system testable at a single seam.

Decisions worth reading before changing anything:

- [ADR 0001](docs/adr/0001-plugin-speaks-hidpp-directly.md) — why the plugin
  speaks HID++ itself instead of driving Solaar.
- [ADR 0002](docs/adr/0002-directions-are-classified-by-dominant-axis.md) — why
  the Direction classifier deliberately diverges from Solaar's, and why that
  looks like a bug if you do not know.
- [Pointer motion under Diversion](docs/findings/pointer-motion-under-diversion.md)
  — what the mouse actually does while the Gesture Button is held, measured.

The vocabulary these use is fixed in [CONTEXT.md](CONTEXT.md).

## Debugging

Run the Helper by hand to watch a Gesture resolve:

```bash
./bin/mx-master-helper           # state on stdout, a log on stderr
./bin/mx-master-helper --once    # one state line, then exit, configuring nothing
```

The long-running form takes the same lock the shell's Helper holds, so starting
one by hand while the shell's is up makes it wait for that one to let go rather
than race it — two Helpers reading the same Control would fire every Gesture
twice. `--once` does not take the lock and never writes to the mouse, so it can
be run at any time; it uses its own software id to keep its replies and the
running Helper's apart.

Besides the lock, the Helper keeps one small file in `$XDG_RUNTIME_DIR`:
which low-battery warnings it has already given. That is runtime state, not
configuration — it is what stops a hot-reload re-announcing a flat mouse, and
it is deliberately not in the plugin folder, where writing anything restarts
the Helper.

Over IPC:

```bash
omarchy-shell vicsvetdev.mx-master status
omarchy-shell vicsvetdev.mx-master refresh
omarchy-shell vicsvetdev.mx-master resolveConflict
```

## Tests

```bash
tests/run.sh
omarchy plugin validate .     # manifest, checked by the thing that enforces it
```

`tests/test-helper.py` drives the real Helper as a subprocess through its one
behavioural seam: a fake device on a socket that the test writes HID++ frames
into and reads device writes back out of, settings on standard input, recording
fakes ahead of the real tools on `PATH`, and published state read off standard
output. It asserts on what the Helper shows the world and never reaches inside
it.

`tests/test-discovery.py` covers choosing an endpoint, which is filesystem
logic and not reachable from that seam, against the report descriptors the real
machine publishes. `tests/test-qml-contracts.sh` pins the agreements between the
QML, the manifest and the Helper that a refactor on either side could silently
break.

The seam is only sufficient while the widget stays a pure projection. A decision
that migrates into the QML leaves the seam and becomes untestable without a
Quickshell harness; that is the tripwire to watch for in review.

## Not in this version

Any Control other than the Gesture Button. Diagonal Directions and multi-stroke
Gestures. Chorded Gestures. Thumb-wheel behaviour. Command and built-in Actions.
Window-gated Bindings. DPI presets. Bluetooth and USB-C. Any other Logitech
device. Pairing — Solaar remains the tool for that.
