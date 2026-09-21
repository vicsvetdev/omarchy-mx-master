---
status: accepted
---

# Directions are classified by dominant axis, not by a rounded unit vector

Solaar resolves a Segment by normalising it and rounding the unit vector onto
one of eight compass points. That is the right shape for a recogniser with
diagonals: each of the eight directions gets a 45° band, and the four diagonals
carry half the angular space.

This plugin has four Directions and no diagonals. Reusing Solaar's classifier
would therefore leave 180° of the circle — every diagonal band — matching
nothing at all. A flick 30° off vertical would resolve to a Direction that has
no Binding, produce no keystroke and no feedback, and be indistinguishable from
a button that had stopped working.

So the Helper classifies by dominant axis instead, giving each Direction a full
quadrant:

    no Segments                    -> Tap
    |x| > |y|, x > 0               -> Right
    |x| > |y|, x < 0               -> Left
    |y| >= |x|, y < 0              -> Up
    |y| >= |x|, y > 0              -> Down

Every angle resolves to something. There are no dead zones between adjacent
Directions, and a roughly-upward flick is up.

## Consequences

The two other pieces inherited from Solaar's recogniser are inherited on
purpose and must stay: the DPI-normalised accumulation, and the discarded first
movement report that works around a firmware quirk specific to the MX Master
3S. Both encode real device knowledge that was expensive to learn.

This one is rejected on purpose, and that asymmetry is the risk this record
exists to cover. A future contributor porting more of Solaar's recogniser will
see the dominant-axis classifier sitting next to two faithful ports, read it as
an oversight, and "fix" it back — silently reintroducing the dead zones, in a
change whose diff looks like it is increasing fidelity to the prior art.

If diagonals are ever added, this decision is worth revisiting rather than
extending: eight Directions want Solaar's classifier back, and the quadrants
would then be the thing that is wrong.
