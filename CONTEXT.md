# MX Master

An Omarchy shell plugin that reads the battery, sets the sensitivity, and
turns thumb gestures into keystrokes for a Logitech MX Master 3S, by speaking
HID++ to the mouse directly rather than through any other device manager.

## Language

### The device

**Control**:
A physically distinct button or wheel that the mouse's firmware exposes as
individually addressable. The MX Master 3S has seven.
_Avoid_: key, button id, CID

**Gesture Button**:
The Control under the thumb rest. The only Control this plugin takes over.
_Avoid_: thumb button, side button, paddle

**Diversion**:
The firmware state in which a Control stops emitting its ordinary input event
and instead reports to whoever is listening over HID++. A Control is either
diverted or it is not; nothing else can use it meanwhile.
_Avoid_: capture, grab, intercept, hook

**Arming**:
Putting the Gesture Button into Diversion and confirming the mouse accepted it.
The mouse forgets Diversion whenever it loses power, so Arming is something
that happens repeatedly, not once.
_Avoid_: enabling, activating, initialising, setup

**DPI**:
The mouse's own hardware pointer resolution, held in firmware, expressed in
steps of 50 between 200 and 8000.
_Avoid_: sensitivity, pointer speed, resolution, accel — "sensitivity" in
particular is the compositor's pointer acceleration, a different setting on a
different layer that this plugin never touches.

### Gestures

**Gesture**:
One complete press-to-release of the Gesture Button, resolved to exactly one
outcome: a Tap or a Direction.
_Avoid_: gesture event, motion, input

**Segment**:
One continuous stroke within a held Gesture, ended by the hand going still.
A Gesture is made of zero or more Segments; zero Segments is a Tap.
_Avoid_: stroke, swipe, move

**Tap**:
The outcome of a Gesture whose movement never crossed the threshold.
_Avoid_: click, press, short press

**Direction**:
The outcome of a Gesture that moved — one of Up, Down, Left, Right.
_Avoid_: swipe, movement, vector

**Binding**:
The stored association between a Gesture outcome and an Action. There are five
possible Bindings, one per outcome, and a Binding may be absent.
_Avoid_: mapping, remap, rule, shortcut, assignment

**Action**:
What a Binding does when it fires.
_Avoid_: command, effect, handler, trigger

### The plugin

**Helper**:
The long-lived process that holds the mouse open — the only thing in the system
that talks to the device.
_Avoid_: daemon, backend, agent, driver

**Service**:
The plugin entry point that owns the Helper's lifetime. Distinct from the
Helper: the Service decides when the Helper exists, the Helper decides what the
mouse does.
_Avoid_: supervisor, manager, host

**Primary Instance**:
The single widget instance elected to own shared state when the bar is drawn on
more than one monitor. The others render and nothing more.
_Avoid_: main widget, first instance, leader

**Conflict**:
The condition in which another program is managing the same mouse. The plugin
refuses to Arm while a Conflict exists rather than competing for the device.
_Avoid_: clash, contention, collision
