# Diversion suppresses ordinary pointer motion

Observed directly against the real MX Master 3S on 2026-09-18, by putting the
Gesture Button (CID `0x00C3`) into Diversion with raw-XY reporting and comparing,
for each press-to-release, the movement the mouse reported over HID++ against the
movement the on-screen pointer actually made.

Fourteen Gestures, each a deliberate few-centimetre stroke:

| raw HID++ delta | on-screen delta |
|-----------------|-----------------|
| (559, 542)      | (0, 11)         |
| (158, -890)     | (-2, 15)        |
| (100, 384)      | (2, -21)        |
| (-579, -116)    | (-1, 12)        |
| (324, -297)     | (0, -1)         |
| (-346, 29)      | (0, 0)          |
| (-134, 2)       | (0, 0)          |
| …               | …               |

**Ordinary pointer motion stops for the duration of the hold.** Hundreds of sensor
counts produce single-digit pixel movement — at 1000 DPI those strokes would
otherwise have carried the pointer several hundred pixels. The pointer does not
travel across the screen as a side effect of gesturing.

The handful of residual pixels is movement reported in the instant between
button-down and the firmware switching into raw-XY reporting. It never exceeded
21 px and was usually zero. It is the same artefact the discarded first movement
report exists for, and is another reason to keep discarding it.

## Consequence for the Tap/Direction threshold

**No change.** The low threshold agreed in the spec stands.

The threshold was kept low because the two error modes are not symmetric: a Tap
closes a tab and a Direction reopens one, so an ambiguous Gesture should resolve
toward the Direction. Nothing in this finding pushes back on that. Had the
pointer kept moving, the threshold would have had to clear whatever cursor travel
a deliberate stroke produced, and a Gesture would have left the pointer somewhere
the user did not put it. It does not, so the threshold answers only to the
Tap/Direction question and can stay where the asymmetry argument puts it.

## Afterwards

The Gesture Button was put back the way it was found. It had arrived carrying
mapping flags `0x01` — Solaar had it diverted — and the investigation restored
exactly that before exiting, confirmed by reading the flags back: `0x11` while
the experiment ran, `0x01` again at the end. No Diversion of this plugin's
making was left on the device.

The investigation code was thrown away, as the ticket asked; this file is its
deliverable.
