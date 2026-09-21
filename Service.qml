import QtQuick
import Quickshell
import Quickshell.Io

// The Service: the Helper's lifetime, and nothing else.
//
// It starts the Helper, restarts it if it exits, and pushes settings to it on
// its standard input. It decides nothing about the mouse — the Helper owns
// every one of those decisions, and this file owns only whether the Helper
// exists. The split matters because the shell mounts a service once per
// session and builds a bar per monitor: one Helper holding the device is the
// difference between a Gesture firing once and firing once per screen.
//
// The Helper reads no configuration file and watches none. Settings arrive
// here from the widget and go down the pipe, so changing a Binding does not
// restart the Helper and does not disturb the mouse.
Item {
  id: root
  width: 0
  height: 0
  visible: false

  property var shell: null
  property var manifest: null
  property var pluginRegistry: null
  property var barWidgetRegistry: null
  property string omarchyPath: ""

  // The last state the Helper published. Every field the widget renders comes
  // from here; the widget adds nothing of its own.
  property var state: ({
    present: false,
    battery: null,
    charging: false,
    dpi: 1000,
    dpiMin: 200,
    dpiMax: 8000,
    dpiStep: 50,
    armed: false,
    status: "offline",
    reason: "Starting up…"
  })

  readonly property bool present: state.present === true
  readonly property var battery: state.battery
  readonly property bool charging: state.charging === true
  readonly property int dpi: Number(state.dpi) || 1000
  readonly property int dpiMin: Number(state.dpiMin) || 200
  readonly property int dpiMax: Number(state.dpiMax) || 8000
  readonly property int dpiStep: Number(state.dpiStep) || 50
  readonly property bool armed: state.armed === true
  readonly property string status: String(state.status || "offline")
  readonly property string reason: state.reason ? String(state.reason) : ""
  // The Bindings in force, so the panel reads them the same way it reads every
  // other published field rather than reaching into the state object itself.
  readonly property var bindings: state.bindings || ({})
  readonly property bool running: helper.running

  readonly property string helperPath:
    Qt.resolvedUrl("bin/mx-master-helper").toString().replace(/^file:\/\//, "")

  // What was last sent down the pipe, so an unchanged push is not resent. The
  // widget exists once per monitor and they all see the same settings.
  property string _lastSent: ""

  function send(message) {
    if (!helper.running) return false
    helper.write(JSON.stringify(message) + "\n")
    return true
  }

  function pushSettings(values) {
    var encoded = JSON.stringify(values)
    if (encoded === root._lastSent) return
    root._lastSent = encoded
    if (root.send({ settings: values })) return
    // The Helper is between lives; it will be handed these when it comes up.
    root._pendingSettings = values
  }

  function command(name) {
    root.send({ cmd: String(name) })
  }

  function resolveConflict() { command("resolveConflict") }
  function refresh() { command("refresh") }

  property var _pendingSettings: null

  function absorb(line) {
    var next
    try {
      next = JSON.parse(line)
    } catch (e) {
      console.warn("mx-master: unreadable state from the helper:", line)
      return
    }
    if (!next || typeof next !== "object") return
    var before = root.state
    root.state = next
    if (before.status !== next.status || before.present !== next.present)
      console.log("mx-master:", next.status, next.reason ? "— " + next.reason : "")
  }

  Process {
    id: helper
    command: [root.helperPath]
    running: true
    stdinEnabled: true

    stdout: SplitParser {
      onRead: function(line) { root.absorb(line) }
    }
    // The Helper logs to stderr, which is how state transitions reach the
    // shell's own log and can be read back after the fact.
    stderr: SplitParser {
      onRead: function(line) { if (line) console.log("mx-master:", line) }
    }

    onStarted: {
      root._lastSent = ""
      if (root._pendingSettings) {
        var values = root._pendingSettings
        root._pendingSettings = null
        root.pushSettings(values)
      }
    }

    onExited: function(exitCode) {
      console.warn("mx-master: helper exited with", exitCode, "— restarting")
      root.state = Object.assign({}, root.state, {
        present: false, battery: null, armed: false,
        status: "offline", reason: "The mouse-side component is restarting."
      })
      restart.restart()
    }
  }

  // A crash loop must not become a fork bomb. The Helper waits for its
  // predecessor to let go of the device anyway, so a slow restart costs
  // nothing that a fast one would have gained.
  Timer {
    id: restart
    interval: 2000
    onTriggered: if (!helper.running) helper.running = true
  }
}
