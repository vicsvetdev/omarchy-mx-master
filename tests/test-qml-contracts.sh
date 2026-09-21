#!/bin/bash
# Static regressions for the agreements between the QML, the manifest, the
# shell configuration and the Helper. Quickshell's typed IpcHandler prevents
# standalone linting of these files, so these pin the things a refactor on
# either side could silently break. They are static assertions, not behavioural
# tests — the behaviour lives in test-helper.py, behind the Helper's one seam.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$here/.."
panel="$root/Panel.qml"
service="$root/Service.qml"
manifest="$root/manifest.json"
helper="$root/bin/mx-master-helper"
pass=0 fail=0

expect() {
  local name="$1" condition="$2"
  if eval "$condition"; then echo "PASS $name"; pass=$((pass + 1))
  else echo "FAIL $name"; fail=$((fail + 1)); fi
}

# The widget renders a projection of one state object. Every field it reads off
# the Service must be one the Helper actually puts in that object, or the panel
# renders undefined and says nothing about why.
published="$(sed -n '/def snapshot/,/^        }$/p' "$helper" \
  | grep -oE '^ +"[a-zA-Z]+":' | tr -d ' ":')"
read_fields="$(grep -oE 'state\.[a-zA-Z]+' "$service" "$panel" \
  | sed -E 's/.*state\.([a-zA-Z]+)/\1/' | sort -u)"
missing=""
for field in $read_fields; do
  printf '%s\n' "$published" | grep -qx "$field" || missing="$missing $field"
done
expect "every state field the QML reads is one the Helper publishes ($(echo $read_fields | tr '\n' ' '))" \
  '[ -z "$missing" ]'

# The Service exposes that state as named properties. Every one of them has to
# derive from the published object rather than from anything this side worked
# out for itself — the two exceptions are about the Helper's lifetime, which is
# the Service's own business and not the mouse's.
invented=""
while IFS= read -r line; do
  name="$(sed -E 's/.*readonly property [a-zA-Z]+ ([a-zA-Z]+):.*/\1/' <<<"$line")"
  case "$name" in running | helperPath) continue ;; esac
  grep -q 'state\.' <<<"$line" || invented="$invented $name"
done < <(grep -E '^[[:space:]]+readonly property ' "$service")
expect "every property the Service exposes is read off the published state" \
  '[ -z "$invented" ]'

# The plugin id is load-bearing in four places; they must agree.
id="$(grep -oE '"id": *"[^"]+"' "$manifest" | head -1 | sed -E 's/.*: *"([^"]+)"/\1/')"
expect "manifest id, moduleName and ipcTarget agree ($id)" \
  'grep -q "moduleName: \"$id\"" "$panel" && grep -q "ipcTarget: \"$id\"" "$panel"'
expect "the widget looks its own service up by that same id" \
  'grep -q "serviceFor(root.moduleName)" "$panel"'

# The Helper names its lock and its remembered battery edges after the same id.
# Two Helpers that disagree about the lock file would both hold the mouse and
# fire every Gesture twice.
expect "the Helper's own idea of the plugin id agrees with the manifest" \
  'grep -q "^PLUGIN_ID = \"$id\"$" "$helper"'

# Both kinds this plugin declares need an entry point, and the service entry
# point is what mounts the Helper's owner once per session rather than per
# monitor.
expect "the manifest declares both a service and a bar widget" \
  'grep -q "\"service\"" "$manifest" && grep -q "\"bar-widget\"" "$manifest"'
expect "the service entry point is the file that owns the Helper" \
  'grep -q "\"service\": \"Service.qml\"" "$manifest" && grep -q "Process {" "$service"'

# The Helper is spawned by path from the Service; a rename on either side leaves
# a plugin that loads and never says anything.
expect "the helper the Service spawns exists and is executable" \
  '[ -x "$helper" ] && grep -q "bin/mx-master-helper" "$service"'
expect "the Helper is spawned with a pipe to write settings into" \
  'grep -q "stdinEnabled: true" "$service"'

# Every scalar setting the QML reads must be declared in the manifest schema, or
# the ordinary settings UI silently drifts from what the widget consumes.
# `bindings` is deliberately absent: the manifest schema supports only scalar
# types, and Bindings are edited in this plugin's own panel.
setting_keys="$(grep -oE 'setting\("[A-Za-z]+"' "$panel" \
  | sed -E 's/setting\("([A-Za-z]+)"/\1/' | sort -u)"
missing=""
for key in $setting_keys; do
  [ "$key" = "bindings" ] && continue
  grep -q "\"key\": \"$key\"" "$manifest" || missing="$missing $key"
done
expect "every scalar setting the QML reads is declared in the manifest schema" \
  '[ -z "$missing" ]'
expect "Bindings are not declared as a manifest scalar" \
  '! grep -q "\"key\": \"bindings\"" "$manifest"'

# No decision about what to display lives in the QML. The widget hides because
# the Helper said the mouse is not there, not because the widget worked it out.
expect "the widget's visibility is the Helper's answer, not the widget's" \
  'grep -q "visible: root.present" "$panel" && grep -q "property bool present: service ? service.present" "$panel"'
expect "the DPI range comes off the device rather than being written in here" \
  'grep -q "minimum: root.dpiMin" "$panel" && grep -q "maximum: root.dpiMax" "$panel" \
   && grep -q "service.dpiMin" "$panel" && grep -q "service.dpiMax" "$panel"'
expect "the panel shows the Bindings the Helper holds, not a second copy of them" \
  'grep -q "readonly property var bindings: service ? service.bindings" "$panel" \
   && grep -q "readonly property var bindings: state.bindings" "$service"'

# Every Service property the panel reads must exist on the Service, or the panel
# renders undefined and says nothing about why.
service_names="$(grep -oE '\breadonly property [a-zA-Z]+ [a-zA-Z]+:' "$service" \
  | sed -E 's/.* ([a-zA-Z]+):/\1/'; echo state; echo pushSettings; echo refresh; echo resolveConflict; echo command)"
missing=""
for name in $(grep -oE 'service\.[a-zA-Z]+' "$panel" | sed -E 's/service\.//' | sort -u); do
  printf '%s\n' "$service_names" | grep -qx "$name" || missing="$missing $name"
done
expect "every Service member the panel reaches for actually exists" '[ -z "$missing" ]'

# The panel builds the record that gets stored in shell.json. The Helper is what
# reads it back, so the two have to agree on its shape — a Binding carrying an
# Action tagged by type, and the window-match field the spec keeps empty.
expect "the Binding record the panel stores is the shape the Helper reads" \
  'grep -q "return { window: \"\", action: { type: \"keystroke\", keys:" "$panel" \
   && grep -q "binding.get(\"action\")" "$helper" \
   && grep -q "action.get(\"keys\")" "$helper" \
   && grep -q "\"window\": \"\"" "$helper"'

# The base Panel would publish a second IpcHandler for the same target.
expect "base panel IPC stays off next to the widget's own handler" \
  'grep -q "manageIpc: false" "$panel" && grep -q "IpcHandler {" "$panel"'

# Omarchy instantiates the widget once per monitor. Two IpcHandlers on one
# target is a bug in Omarchy's book, so that stays single-owner.
expect "the IPC target is claimed by a single primary instance" \
  'grep -q "property bool primaryInstance" "$panel" \
   && grep -q "enabled: root.primaryInstance" "$panel"'

# The settings push is deliberately NOT gated on that election. It picks the
# instance on the first screen, so a bar not drawn there would elect nobody and
# push nothing — leaving the Helper with no configuration at all. Duplicate
# pushes are free because the Service drops one identical to the last.
expect "the settings push is not gated on the election, and duplicates are dropped" \
  '! grep -q "primaryInstance) return" "$panel" && grep -q "_lastSent" "$service"'

# Configuration is written through the shell's plugin configuration API, into
# the shell's own file. A file written inside the plugin directory would trip
# the shell's plugin hot-reload and restart the Helper on every settings change.
expect "settings are written through the shell's configuration API" \
  'grep -q "updateEntryInline(root.moduleName" "$panel"'
expect "nothing writes a configuration file inside the plugin directory" \
  '! grep -qE "FileView|writeAdapter|\.open\(.*WriteOnly" "$panel" "$service"'
expect "the Helper reads no configuration file and watches none" \
  '! grep -qE "MX_MASTER_CONFIG|config\.json|\.yaml" "$helper"'

# The one file the Helper does keep is which battery warnings it has already
# given — runtime state, so that a hot-reload does not re-announce a flat mouse.
# It belongs beside the lock file, never inside the plugin folder.
expect "remembered battery warnings live in the runtime directory, not the plugin folder" \
  'grep -q "runtime_dir(), f\"{PLUGIN_ID}.state\"" "$helper" \
   && ! grep -qE "state_path.*Qt.resolvedUrl|state_path.*__file__" "$helper"'

# The five Binding slots the panel offers must be the five outcomes the Helper
# resolves a Gesture to, or a slot is editable and never fires.
helper_outcomes="$(grep -oE '^OUTCOMES = \(.*\)$' "$helper" | grep -oE '"[a-z]+"' | tr -d '"' | sort)"
panel_slots="$(grep -oE '\{ key: "[a-z]+", label: "[A-Za-z]+" \}' "$panel" \
  | sed -E 's/.*key: "([a-z]+)".*/\1/' | sort)"
expect "the panel's Binding slots are exactly the Helper's Gesture outcomes" \
  '[ "$helper_outcomes" = "$panel_slots" ]'

# Every modifier the panel can store must be one the virtual-keyboard tool
# answers to. It refuses "super" outright, and a Binding that names the key its
# owner knows would do nothing with nothing to show for it.
mods="$(grep -oE 'keys: \[[^]]*\]' "$panel" | grep -oE '"[a-z]+"' | tr -d '"' | sort -u)"
bad=""
for mod in $mods; do
  case "$mod" in
    shift|capslock|ctrl|logo|win|alt|altgr) ;;
    *) grep -q "\"$mod\": \"" "$helper" && bad="$bad $mod" ;;
  esac
done
expect "the panel offers no modifier the keystroke tool would refuse" '[ -z "$bad" ]'
expect "the Helper translates the modifier names people actually write" \
  'grep -q "\"super\": \"logo\"" "$helper"'

# Keystrokes go through the Wayland virtual-keyboard path. Synthesising
# kernel-level key events would deliver a different keysym the moment the
# Cyrillic layout was in front.
expect "keystrokes go through the virtual-keyboard tool and nothing else" \
  'grep -q "KEYSTROKE_TOOL = \"wtype\"" "$helper" \
   && grep -q "argv = \[KEYSTROKE_TOOL\]" "$helper" \
   && ! grep -q "ydotool\|uinput" "$helper"'

# The plugin installs as a folder with no build step and needs no root.
expect "the plugin needs no build step" \
  '[ ! -f "$root/Makefile" ] && [ ! -f "$root/package.json" ] && [ ! -f "$root/meson.build" ]'
expect "nothing asks for root" \
  '! grep -rqE "\bsudo\b|\bpkexec\b" "$helper" "$panel" "$service"'

echo "----"
echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
