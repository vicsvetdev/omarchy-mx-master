import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// MX Master: the mouse's battery on the bar, a panel for its DPI and its
// gesture Bindings, and a line saying whether gestures are armed.
//
// Everything on screen here is a projection of the single state object the
// Helper publishes. Nothing in this file decides anything about the mouse —
// not whether to show the widget (the Helper computes `present`), not which
// DPI values are offered (the Helper reads the range off the device), not what
// a Gesture does (the Helper owns Binding lookup and Action dispatch). That is
// load-bearing rather than stylistic: it is what keeps the whole system
// testable at one seam. A decision that migrates into this file leaves the
// seam and becomes untestable without a Quickshell harness.
//
// Glyphs are \u escapes rather than literal characters, so the source survives
// editors and patches that mangle private-use codepoints.
Panel {
  id: root

  moduleName: "vicsvetdev.mx-master"
  ipcTarget: "vicsvetdev.mx-master"
  // The base Panel would publish open/close/toggle for this target; the
  // handler below does that and more, so keep the base one off.
  manageIpc: false

  readonly property string mouseGlyph: "󰍽"     // nf-md-mouse
  readonly property string chargingGlyph: "󰒥"  // nf-md-power-plug

  // Omarchy builds one bar — and so one instance of this widget — per monitor.
  // The mouse is one device on one seat, so exactly one instance owns the IPC
  // target and the settings pushed to the Helper; the rest only render.
  // Without this, N monitors mean N duplicate handlers on one target.
  readonly property bool primaryInstance: {
    var w = root.QsWindow.window
    var screens = Quickshell.screens
    if (!w || !w.screen || screens.length === 0) return true
    return String(w.screen.name) === String(screens[0].name)
  }

  // ----------------------------------------------------------------- settings

  readonly property bool showPercent: setting("showPercent", true) === true
  readonly property int lowBattery: Number(setting("lowBattery", 20)) || 20
  readonly property int criticalBattery: Number(setting("criticalBattery", 10)) || 10
  readonly property int configuredDpi: Number(setting("dpi", 1000)) || 1000

  // While the slider is being dragged this carries the value the mouse should
  // already feel, before it is written to the shell's configuration on release.
  property int liveDpi: -1

  // True while a slot's picker owns the keys, so the panel's own j/k does not
  // drive the cursor at the same time as the popup's.
  property bool pickerOpen: false

  signal openSlotPicker(int index)

  // -------------------------------------------------------------- the Helper
  //
  // The Helper is owned by the Service, not by this widget. A Process in here
  // would be one Helper per monitor, and two Helpers reading the same Control
  // means every Gesture firing twice.
  property var service: null

  function bindService() {
    if (root.service) { root.pushSettings(); return }
    var host = bar && bar.shell ? bar.shell : null
    if (!host || typeof host.serviceFor !== "function") return
    var found = host.serviceFor(root.moduleName)
    if (!found) return
    root.service = found
    root.pushSettings()
  }

  // Deliberately not gated on primaryInstance: the election picks the instance
  // on the first screen, and a bar that is not drawn there would elect nobody
  // and push nothing. Every instance pushes the same values and the Service
  // drops a push identical to the last, so duplicates cost nothing — whereas a
  // Helper that never learns its settings is the whole plugin not working.
  function pushSettings() {
    if (!root.service) return
    // `bindings` is null until something has been changed in the panel, and a
    // null leaves the Helper on the Bindings it ships with rather than making
    // this file keep a second copy of them.
    root.service.pushSettings({
      dpi: root.liveDpi >= 0 ? root.liveDpi : root.configuredDpi,
      lowBattery: root.lowBattery,
      criticalBattery: root.criticalBattery,
      bindings: root.setting("bindings", null)
    })
  }

  Timer {
    interval: 200
    running: root.service === null
    repeat: true
    onTriggered: root.bindService()
  }

  onBarChanged: bindService()
  onSettingsChanged: pushSettings()
  onLiveDpiChanged: pushSettings()

  // ------------------------------------------------------ what the Helper says

  readonly property bool present: service ? service.present : false
  readonly property var battery: service ? service.battery : null
  readonly property bool charging: service ? service.charging : false
  readonly property int deviceDpi: service ? service.dpi : 1000
  readonly property int dpiMin: service ? service.dpiMin : 200
  readonly property int dpiMax: service ? service.dpiMax : 8000
  readonly property int dpiStep: service ? service.dpiStep : 50
  readonly property bool armed: service ? service.armed : false
  readonly property string status: service ? service.status : "offline"
  readonly property string reason: service ? service.reason : ""
  readonly property var bindings: service ? service.bindings : ({})

  readonly property string batteryText:
    battery === null || battery === undefined ? "—" : String(battery) + "%"
  readonly property bool batteryLow: battery !== null && battery !== undefined
    && battery <= root.lowBattery && !root.charging

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  // ---------------------------------------------------------------- persisting
  //
  // Settings live in the shell's own configuration file, nested under this
  // plugin's bar entry, and are written through the shell's plugin
  // configuration API. Nothing is written inside the plugin directory: saving
  // a file there triggers the shell's plugin hot-reload, which would restart
  // the Helper every time a setting changed — a restart loop built into the
  // settings panel.
  function saveSettings(changes) {
    var host = bar && bar.shell ? bar.shell : null
    if (!host || typeof host.updateEntryInline !== "function") return false
    var next = ({})
    for (var key in root.settings) if (key !== "id") next[key] = root.settings[key]
    for (var changed in changes) next[changed] = changes[changed]
    return host.updateEntryInline(root.moduleName, next)
  }

  // ----------------------------------------------------------------- Actions
  //
  // Every entry produces a keystroke Action, stored as a tagged union so that
  // command and built-in Actions can arrive later as new variants rather than
  // as a redesign. `value` is the stored key list joined, so a Binding written
  // by hand into shell.json still shows itself here even when it is not one of
  // these. Modifier names are the ones the virtual-keyboard tool answers to.
  readonly property var actionCatalogue: [
    { value: "", label: "Nothing", keys: [] },
    { value: "ctrl+w", label: "Close tab", keys: ["ctrl", "w"] },
    { value: "ctrl+shift+t", label: "Reopen closed tab", keys: ["ctrl", "shift", "t"] },
    { value: "ctrl+t", label: "New tab", keys: ["ctrl", "t"] },
    { value: "ctrl+Tab", label: "Next tab", keys: ["ctrl", "Tab"] },
    { value: "ctrl+shift+Tab", label: "Previous tab", keys: ["ctrl", "shift", "Tab"] },
    { value: "alt+Left", label: "Back", keys: ["alt", "Left"] },
    { value: "alt+Right", label: "Forward", keys: ["alt", "Right"] },
    { value: "ctrl+r", label: "Reload", keys: ["ctrl", "r"] }
  ]

  readonly property var bindingSlots: [
    { key: "tap", label: "Tap" },
    { key: "up", label: "Up" },
    { key: "down", label: "Down" },
    { key: "left", label: "Left" },
    { key: "right", label: "Right" }
  ]

  function keysFor(outcome) {
    var binding = root.bindings ? root.bindings[outcome] : null
    if (!binding || !binding.action || binding.action.type !== "keystroke") return []
    return binding.action.keys || []
  }

  function valueFor(outcome) {
    return root.keysFor(outcome).join("+")
  }

  function bindingFor(value) {
    if (!value) return null
    for (var i = 0; i < root.actionCatalogue.length; i++) {
      if (root.actionCatalogue[i].value === value) {
        // The window-match field exists so gating on the focused window can
        // return later without reshaping stored configuration. It is empty,
        // and nothing consults it yet.
        return { window: "", action: { type: "keystroke", keys: root.actionCatalogue[i].keys } }
      }
    }
    return null
  }

  function setBinding(outcome, value) {
    var next = ({})
    for (var i = 0; i < root.bindingSlots.length; i++) {
      var name = root.bindingSlots[i].key
      var current = root.bindings ? root.bindings[name] : null
      next[name] = name === outcome ? root.bindingFor(value) : (current || null)
    }
    root.saveSettings({ bindings: next })
  }

  // ------------------------------------------------------------------- cursor
  //
  // One cursor for keyboard and mouse both, per the CursorSurface contract:
  // hover and key presses move the same root-level state, so exactly one row is
  // highlighted however it got there. Row 0 is the DPI slider when the mouse is
  // there at all; the rest are the Binding slots.
  property int cursorIndex: -1
  property bool cursorActive: false
  readonly property int firstSlotRow: root.present ? 1 : 0
  readonly property int rowCount: root.firstSlotRow + root.bindingSlots.length

  function moveCursor(dy) {
    if (root.rowCount === 0) return
    root.cursorActive = true
    if (root.cursorIndex < 0) root.cursorIndex = 0
    else root.cursorIndex = Math.max(0, Math.min(root.rowCount - 1, root.cursorIndex + dy))
  }

  function nudgeDpi(direction) {
    if (!root.present) return
    var from = root.liveDpi >= 0 ? root.liveDpi : root.configuredDpi
    root.commitDpi(Math.max(root.dpiMin, Math.min(root.dpiMax, from + direction * root.dpiStep)))
  }

  function commitDpi(value) {
    // Keep the dragged value in force until the configuration round-trip brings
    // it back. Clearing it first would push the pre-drag DPI at the mouse in
    // between, and the pointer would lurch back before settling.
    root.liveDpi = Math.round(value)
    root.saveSettings({ dpi: Math.round(value) })
  }

  onConfiguredDpiChanged: if (root.liveDpi >= 0 && root.configuredDpi === root.liveDpi) {
    root.liveDpi = -1
  }

  function activateCursor() {
    if (!root.cursorActive || root.cursorIndex < root.firstSlotRow) return
    root.openSlotPicker(root.cursorIndex - root.firstSlotRow)
  }

  // ------------------------------------------------------------------ the bar

  // The widget is hidden entirely — not greyed, not zero — when the mouse is
  // not there. `present` is the Helper's answer, not this file's.
  visible: root.present
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onOpenedChanged: if (opened) {
    root.cursorActive = false
    root.cursorIndex = -1
    if (root.service) root.service.refresh()
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  IpcHandler {
    // Only one instance may claim the target — two handlers on one target is a
    // bug in Omarchy's book, and the mouse is seat-global anyway.
    enabled: root.primaryInstance
    target: root.ipcTarget

    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    // The Helper's own published state, verbatim — re-listing the fields here
    // would be a second copy of a shape that has one owner.
    function status(): string {
      return JSON.stringify(root.service ? root.service.state : {})
    }
    function refresh(): string {
      if (!root.service) return "error: the helper is not up yet"
      root.service.refresh()
      return "ok"
    }
    function resolveConflict(): string {
      if (!root.service) return "error: the helper is not up yet"
      if (root.status !== "conflict") return "no conflict"
      root.service.resolveConflict()
      return "ok"
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    // The hidden label sizes the slot; the row below paints it, so the glyph
    // and the number can carry the sizes the rest of the bar uses for each.
    text: root.mouseGlyph + (root.showPercent ? " " + root.batteryText : "")
    labelVisible: false
    fontSize: Style.font.body
    horizontalMargin: 7
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) root.saveSettings({ showPercent: !root.showPercent })
      else root.toggle()
    }

    Row {
      anchors.centerIn: parent
      spacing: Style.space(4)

      Text {
        anchors.verticalCenter: parent.verticalCenter
        text: root.mouseGlyph
        color: root.batteryLow ? root.urgent : button.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.bar.iconFont
        renderType: Text.NativeRendering
      }

      Text {
        anchors.verticalCenter: parent.verticalCenter
        // Box-centering puts cap-height ink a hair above the optical center the
        // bar icons sit on; one pixel down lines the number up with them.
        anchors.verticalCenterOffset: 1
        visible: root.showPercent
        text: root.batteryText + (root.charging ? root.chargingGlyph : "")
        color: root.batteryLow ? root.urgent : button.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
        renderType: Text.NativeRendering
      }
    }
  }

  // ---------------------------------------------------------------- the panel

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(520))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: root.pickerOpen
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onMoveRequested: function(dx, dy) {
        if (dy !== 0) root.moveCursor(dy)
        else if (dx !== 0 && root.cursorActive && root.cursorIndex === 0) root.nudgeDpi(dx)
      }
      onActivateRequested: root.activateCursor()
      onTextKey: function(t) {
        if ((t === "r" || t === "R") && root.service) root.service.refresh()
      }

      Column {
        id: column
        width: parent.width
        spacing: Style.space(12)

        PanelHero {
          id: hero
          width: parent.width
          title: "MX Master 3S"
          meta: root.charging ? root.batteryText + " · charging" : root.batteryText
          detail: root.present ? String(root.deviceDpi) + " DPI" : ""
          foreground: root.batteryLow ? root.urgent : root.foreground
          fontFamily: root.fontFamily
          iconComponent: Component {
            Text {
              text: root.mouseGlyph
              color: root.batteryLow ? root.urgent : root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.display
            }
          }
        }

        // Whether gestures are armed, and why not when they are not — so that
        // "working" can be told from "silently not working".
        Column {
          width: parent.width
          spacing: Style.space(8)

          Text {
            textFormat: Text.PlainText
            width: parent.width
            text: root.armed ? "Gestures armed" : (root.reason || "Gestures are not armed")
            color: root.armed ? root.dim : root.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }

          // One action that resolves the common case. It turns off the other
          // program's autostart and stops it; that program's own configuration
          // file is left alone.
          Button {
            visible: root.status === "conflict"
            width: parent.width
            bordered: true
            leftAlign: true
            text: "Turn off Solaar's autostart and stop it"
            foreground: root.foreground
            fontFamily: root.fontFamily
            fontSize: Style.font.bodySmall
            onClicked: if (root.service) root.service.resolveConflict()
          }
        }

        PanelSeparator {
          visible: root.present
          foreground: root.foreground
        }

        // No DPI control is offered while the mouse is unavailable, so the
        // panel never presents a control that cannot do anything.
        Column {
          visible: root.present
          width: parent.width
          spacing: Style.space(6)

          PanelSectionHeader {
            text: "DPI"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          CursorSurface {
            width: parent.width
            height: Style.space(40)
            foreground: root.foreground
            hasCursor: root.cursorActive && root.cursorIndex === 0

            PanelSlider {
              id: dpiSlider
              anchors.left: parent.left
              anchors.leftMargin: Style.space(8)
              anchors.right: dpiValue.left
              anchors.rightMargin: Style.space(10)
              anchors.verticalCenter: parent.verticalCenter
              bar: root.bar
              integer: true
              minimum: root.dpiMin
              maximum: root.dpiMax
              step: root.dpiStep
              value: root.liveDpi >= 0 ? root.liveDpi : root.configuredDpi
              // Dragging changes how the pointer moves as you drag, so the
              // right value can be found by feel. The Helper throttles what
              // the mouse actually sees; binding a device write to slider
              // movement would issue on the order of a hundred and sixty of
              // them in a single drag.
              onMoved: function(v) {
                root.cursorActive = true
                root.cursorIndex = 0
                root.liveDpi = Math.round(v / root.dpiStep) * root.dpiStep
              }
              onReleased: function(v) {
                root.commitDpi(Math.round(v / root.dpiStep) * root.dpiStep)
              }
            }

            Text {
              id: dpiValue
              anchors.right: parent.right
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: String(root.liveDpi >= 0 ? root.liveDpi : root.deviceDpi)
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
            }
          }
        }

        PanelSeparator { foreground: root.foreground }

        // All five Binding slots, what each does, and which are empty.
        Column {
          width: parent.width
          spacing: Style.space(6)

          PanelSectionHeader {
            text: "GESTURES"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Column {
            id: slotColumn
            width: parent.width
            spacing: Style.space(2)

            Repeater {
              model: root.bindingSlots

              delegate: CursorSurface {
                id: slotRow
                required property int index
                required property var modelData

                width: slotColumn.width
                height: Style.space(38)
                foreground: root.foreground
                hasCursor: root.cursorActive
                  && root.cursorIndex === root.firstSlotRow + slotRow.index

                Connections {
                  target: root
                  function onOpenSlotPicker(which) {
                    if (which === slotRow.index) picker.open()
                  }
                }

                MouseArea {
                  anchors.fill: parent
                  hoverEnabled: true
                  acceptedButtons: Qt.NoButton
                  onContainsMouseChanged: if (containsMouse) {
                    root.cursorActive = true
                    root.cursorIndex = root.firstSlotRow + slotRow.index
                  }
                }

                Text {
                  anchors.left: parent.left
                  anchors.leftMargin: Style.space(8)
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  text: slotRow.modelData.label
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                }

                Dropdown {
                  id: picker
                  anchors.right: parent.right
                  anchors.rightMargin: Style.space(6)
                  anchors.verticalCenter: parent.verticalCenter
                  width: Style.space(200)
                  showLabel: false
                  fontFamily: root.fontFamily
                  options: root.actionCatalogue
                  hasCursor: slotRow.hasCursor
                  onChanged: function(next) { root.setBinding(slotRow.modelData.key, next) }
                  onHovered: function(on) {
                    if (on) {
                      root.cursorActive = true
                      root.cursorIndex = root.firstSlotRow + slotRow.index
                    }
                  }
                  onPopupOpenChanged: root.pickerOpen = picker.popupOpen
                }

                // Dropdown assigns its own `value` when a row is picked, which
                // would break a declarative binding and leave the control
                // showing a choice the Helper never accepted. A Binding element
                // keeps re-applying what the Helper actually published.
                Binding {
                  target: picker
                  property: "value"
                  value: root.valueFor(slotRow.modelData.key)
                }
              }
            }
          }
        }
      }
    }
  }
}
