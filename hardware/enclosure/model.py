#!/usr/bin/env python3
"""Base and pan-tilt head for the Pro Max baseboard. Needs CadQuery; writes STEP and STL to out/.

Axes: x runs from side D to side B, y from side A (back: Ethernet, power) to side C (front),
z up from the desk. The origin is the baseboard's corner at sides D and A, on the desk.
Board positions come from hardware/promax-baseboard/gen_pcb.py; keep the two in step.

Printed parts and how they lie on the bed:
  base_bottom   floor down
  base_shell    roof down
  pedestal      floor down; screwed to the roof, holds the pan servo
  yoke          plate down; carries the tilt servo on one arm
  head_front    front face down
  head_back     back face down
  cap_power, cap_small (two)   top down
"""
import math
import os
import sys

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))

# Where the buttons, card slot and lights sit; pick one on the command line.
# buttons: power, network, safe stop as (x, y, hole radius); card: slot x range; lights: x of each.
# pan: where the pan axis stands. Only "corner" matches the board as placed.
LAYOUTS = {
    "middle": {"buttons": [(67, 12, 5.2), (67, 30, 3.8), (67, 44, 3.8)], "card": (52, 65), "lights": (20, 28, 36),
               "pan": (32, 36)},
    "front": {"buttons": [(46, 65, 5.2), (57, 65, 3.8), (67, 65, 3.8)], "card": (6, 19), "lights": (26, 33, 40),
              "pan": (32, 36)},
    # Pan axis in the corner of sides D and C, so the head looks down past two near edges.
    # Buttons in a column beside the Pro Max, clear of the turntable.
    "corner": {"buttons": [(67, 12, 5.2), (67, 30, 3.8), (67, 44, 3.8)], "card": (53, 66.2), "lights": (20, 28, 36),
               "pan": (27, 49)},
}
LAYOUT = sys.argv[1] if len(sys.argv) > 1 else "corner"

# ---- Baseboard and what stands on it --------------------------------------
PCB_X, PCB_Y, PCB_T = 100.0, 72.0, 1.6
HOLES = [(4, 4), (4, 68), (72, 4), (72, 68)]   # M2.5 x 12 self-tapping, from below into the shell
PROMAX_X0 = 77.0        # left edge of the Pro Max; it is 21 wide and as long as the baseboard
SOCKET_H = 11.0         # baseboard top to Pro Max underside, on 8.5 mm sockets
RJ45_TOP = 13.4         # above the Pro Max top face
JACK_X, JACK_W, JACK_H = 19.0, 9.4, 11.0        # barrel jack; its face is flush with the outer wall
TERMINAL_X = 38.0
SWITCH_TOP = 4.9        # tactile switch, top of its plunger above the board
LATCH_TOP, LATCH_STEM = 14.0, 4.0               # latching switch: stem top when out, stem width

# ---- Base ------------------------------------------------------------------
WALL, FLOOR, ROOF = 2.4, 2.4, 2.4
STANDOFF = 4.0
GAP_X, GAP_Y = 0.6, 1.4  # cavity past the board; in y this also covers the connector overhang
PCB_Z = FLOOR + STANDOFF
BOARD = PCB_Z + PCB_T    # top face of the baseboard
PROMAX_Z = BOARD + SOCKET_H
CEILING = PROMAX_Z + 1.0 + RJ45_TOP + 1.0
TOP = CEILING + ROOF
TUBE = 10.0              # button guide tubes hang this far below the ceiling

# ---- Servo: EMAX ES08MA II. Numbers are the drawing's; those marked "scaled" were measured off it ---
SERVO_L, SERVO_W, SERVO_H = 23.0, 11.5, 24.0
SERVO_TAB_Z, SERVO_TAB_L = 15.0, 32.5   # tabs: underside above the case bottom, tip to tip
SERVO_TAB_T = 1.8       # scaled
SERVO_HOLES = 27.6
SERVO_SHAFT = 5.75      # shaft axis from the near end of the body
SERVO_UP = SERVO_H - SERVO_TAB_Z   # top of the gear housing above the underside of the tabs
SERVO_CASE = 19.65 - SERVO_TAB_Z   # the lower part of the case top, beside the gear housing
SERVO_GEAR_L = 14.6     # scaled: the gear housing covers this much of the length, from the shaft end
SERVO_SPLINE = 3.7      # scaled: shaft above the gear housing
SERVO_FIT = 0.3
# Horn: a 15T aluminium disc bought for this servo, 18 mm across, twelve M2 threads. Opposite outer
# holes are 14.8 or 14 mm apart, so parts take screws at DISC_HOLES / 2 with room for either.
DISC_D, DISC_HOLES = 18.0, 14.6
DISC_T, DISC_HUB = 2.0, 1.1    # from the seller: the plate, and the hub standing out of its back (3.1 in all)
DISC_SEAT = 1.0                # guessed: the hub's end above the gear housing once pushed home; measure the part
DISC_UP = DISC_SEAT + DISC_HUB + DISC_T   # the disc's outer face above the gear housing

# ---- Pan-tilt ----------------------------------------------------------------
PAN_X, PAN_Y = LAYOUTS[LAYOUT]["pan"]
RING_R, RING_H = 26.0, 20.0  # pedestal on the roof. Tall, to look down from a fridge top
RING_WALL, RING_FLOOR = 2.4, 2.0
PED_SCREWS = [(16, 8), (-16, 8), (13, -13), (-13, -13)]   # M2.5 x 8 into bosses under the roof
CABLE = (-6.5, -18.0, 6.5, -12.0)   # cable hole behind the pan axis: x0, y0, x1, y1 from the axis
YOKE_T = 6.5
YOKE_Z = TOP + RING_H + 0.4
HEAD_W, HEAD_D, HEAD_H = 40.0, 30.0, 32.0   # camera block; the tilt axis runs through its centre
SLAB_D, SLAB_H = 9.0, 32.0                  # thin upper part for the OLED, flush with the front
ARM_IN = HEAD_W / 2 + 1.0    # inner faces of the yoke arms
ARM_T, ARM_SERVO_T = 4.0, SERVO_UP - SERVO_TAB_T   # servo arm: as thick as the case above its tabs, so it ends flush
TILT_Z = 24.0                # tilt axis above the yoke plate; the block's corners swing 22 mm

# ---- Camera (SC3336 B) and OLED module, from their drawings ------------------
CAM_W, CAM_H, CAM_LENS = 25.0, 24.0, 14.0
CAM_AXIS = 8.5               # lens axis below the board's top edge
CAM_DEPTH = 23.95            # lens front to the front face of the camera board
OLED_W, OLED_H = 27.3, 27.8
OLED_AA = (21.74, 10.86, 6.37)  # active area: width, height, top edge below the board top

# ---- Head interior, in head coordinates (origin on the tilt axis) -------------
HEAD_WALL = 2.0
HEAD_Z = YOKE_Z + YOKE_T + TILT_Z
CAM_Z = -HEAD_H / 2 + 4 + CAM_H - CAM_AXIS   # lens axis
OLED_TOP = HEAD_H / 2 + SLAB_H - 2.1         # top edge of the OLED board
POSTS = [(sx * 15.5, sz * 12.25) for sx in (-1, 1) for sz in (-1, 1)]   # M2 x 8 screws joining the halves


def box(x0, y0, z0, x1, y1, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def cyl(x, y, z0, z1, r):
    return cq.Workplane("XY").circle(r).extrude(z1 - z0).translate((x, y, z0))


def cylx(x0, x1, y, z, r):
    return cq.Workplane("YZ").circle(r).extrude(x1 - x0).translate((x0, y, z))


def cyly(x, y0, y1, z, r):
    return cq.Workplane("XZ").circle(r).extrude(-(y1 - y0)).translate((x, y0, z))


def sector(a0, a1, r, z0, z1):
    """Pie slice around the z axis from angle a0 to a1, degrees."""
    n = max(2, int((a1 - a0) / 10) + 1)
    pts = [(0, 0)] + [(r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
                       r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    return cq.Workplane("XY").polyline(pts).close().extrude(z1 - z0).translate((0, 0, z0))


def at_pan(shape, z=0.0):
    return shape.translate((PAN_X, PAN_Y, z))


def servo():
    """Servo with its shaft axis on the z axis, the long end towards +x and the tab underside at z = 0."""
    s = box(-SERVO_SHAFT, -SERVO_W / 2, -SERVO_TAB_Z, SERVO_L - SERVO_SHAFT, SERVO_W / 2, SERVO_CASE)
    s = s.union(box(-SERVO_SHAFT, -SERVO_W / 2, SERVO_CASE, SERVO_GEAR_L - SERVO_SHAFT, SERVO_W / 2, SERVO_UP))
    c = SERVO_L / 2 - SERVO_SHAFT
    s = s.union(box(c - SERVO_TAB_L / 2, -SERVO_W / 2, 0, c + SERVO_TAB_L / 2, SERVO_W / 2, SERVO_TAB_T))
    return s.union(cyl(0, 0, SERVO_UP, SERVO_UP + SERVO_SPLINE, 2.4))


def pan_servo():
    """Long end towards the front, case top level with the pedestal's rim."""
    return at_pan(servo().rotate((0, 0, 0), (0, 0, 1), 90), TOP + RING_H - SERVO_UP)


def tilt_servo():
    """On the outside of the side B arm, shaft towards the head, long end down."""
    s = servo().rotate((0, 0, 0), (0, 1, 0), -90).rotate((0, 0, 0), (1, 0, 0), 180)
    return s.translate((PAN_X + ARM_IN + ARM_SERVO_T + SERVO_TAB_T, PAN_Y, HEAD_Z))


def references():
    """Bought parts, for checking fit; not printed."""
    pcb = box(0, 0, PCB_Z, PCB_X, PCB_Y, BOARD)
    # The tall parts on the board: x0, y0, x1, y1, height.
    for x0, y0, x1, y1, h in [
            (JACK_X - JACK_W / 2, -GAP_Y - WALL + 0.3, JACK_X + JACK_W / 2, 10.7, JACK_H),
            (TERMINAL_X - 5, 0.4, TERMINAL_X + 5, 8.0, 10.0),
            (62.75, 7.75, 71.25, 16.25, 8.0), (67 - LATCH_STEM / 2, 10, 67 + LATCH_STEM / 2, 14, LATCH_TOP),
            (64, 27, 70, 33, 3.5), (65.8, 28.8, 68.2, 31.2, SWITCH_TOP),
            (64, 41, 70, 47, 3.5), (65.8, 42.8, 68.2, 45.2, SWITCH_TOP),
            (35.2, 19.2, 41.8, 25.8, 7.7), (46.2, 45.2, 52.8, 51.8, 7.7),          # bulk capacitors
            (15.8, 59.2, 28.2, 64.9, 7.0), (31.6, 57.2, 39.4, 59.8, 8.5), (31.6, 61.3, 39.4, 63.9, 8.5),
            (73, 54.2, 75.6, 61.8, 8.5), (73, 21.9, 75.6, 32.1, 8.5),
            (51, 54.5, 66, 71.5, 1.9), (2, 17.5, 17, 37.5, 4.1)]:
        pcb = pcb.union(box(x0, y0, BOARD, x1, y1, BOARD + h))
    for x in LAYOUTS[LAYOUT]["lights"]:
        pcb = pcb.union(cyly(x, 67.8, 73.2, BOARD + 2.0, 1.5))
    pm = box(PROMAX_X0, 0, PROMAX_Z, PROMAX_X0 + 21, PCB_Y, PROMAX_Z + 1.0)
    pm = pm.union(box(PROMAX_X0 + 2.4, -1.25, PROMAX_Z + 1, PROMAX_X0 + 18.5, 20.4, PROMAX_Z + 1 + RJ45_TOP))
    pm = pm.union(box(PROMAX_X0 + 5.7, 65.6, PROMAX_Z + 0.1, PROMAX_X0 + 15.3, 73.3, PROMAX_Z + 4.25))
    pm = pm.union(box(PROMAX_X0 + 1.6 - 1.3, 21, BOARD, PROMAX_X0 + 1.6 + 1.3, 72, PROMAX_Z))
    pm = pm.union(box(PROMAX_X0 + 19.4 - 1.3, 21, BOARD, PROMAX_X0 + 19.4 + 1.3, 72, PROMAX_Z))
    at = (PAN_X, PAN_Y, HEAD_Z)
    return {"baseboard": pcb, "promax": pm, "pan_servo": pan_servo(), "tilt_servo": tilt_servo(),
            "camera": camera().translate(at), "oled": oled().translate(at)}


def camera():
    """SC3336 module in head coordinates: lens tip flush with the front face."""
    front = HEAD_D / 2
    back = front - CAM_DEPTH              # front face of the camera board
    top = CAM_Z + CAM_AXIS                # top edge of the camera board
    c = box(-CAM_W / 2, back - 1.2, top - CAM_H, CAM_W / 2, back, top)
    c = c.union(box(-7.1, back - 3.2, top - CAM_H, 7.1, back - 1.2, top - CAM_H + 5))      # cable socket
    c = c.union(box(-7, back, CAM_Z - 7, 7, back + 10, CAM_Z + 7))                         # lens holder
    return c.union(cq.Workplane("XZ").circle(CAM_LENS / 2).extrude(-(CAM_DEPTH - 10)).translate((0, back + 10, CAM_Z)))


def oled():
    """OLED module in head coordinates: glass against the inside of the front wall."""
    inside = HEAD_D / 2 - HEAD_WALL
    o = box(-OLED_W / 2, inside - 2.6, OLED_TOP - OLED_H, OLED_W / 2, inside - 1.4, OLED_TOP)
    return o.union(box(-26.7 / 2, inside - 1.4, OLED_TOP - 4.27 - 19.26, 26.7 / 2, inside, OLED_TOP - 4.27))


def outline():
    return -GAP_X - WALL, -GAP_Y - WALL, PCB_X + GAP_X + WALL, PCB_Y + GAP_Y + WALL


def base_bottom():
    """Floor plate with the board standoffs; the shell drops over it and four screws clamp all three."""
    x0, y0, x1, y1 = outline()
    p = box(x0, y0, 0, x1, y1, FLOOR).edges("|Z").fillet(4.0)
    for x, y in HOLES:
        p = p.union(cyl(x, y, FLOOR, PCB_Z, 3.2)).cut(cyl(x, y, 0, PCB_Z, 1.45)).cut(cyl(x, y, 0, 1.4, 2.6))
    # Fills the wall's notch under the barrel jack.
    return p.union(box(JACK_X - JACK_W / 2 - 0.2, y0, FLOOR, JACK_X + JACK_W / 2 + 0.2, -GAP_Y, BOARD - 0.2))


def base_shell():
    """Walls and roof in one piece, with every opening."""
    ix0, iy0, ix1, iy1 = -GAP_X, -GAP_Y, PCB_X + GAP_X, PCB_Y + GAP_Y
    lay = LAYOUTS[LAYOUT]
    s = box(ix0 - WALL, iy0 - WALL, FLOOR, ix1 + WALL, iy1 + WALL, TOP).edges("|Z").fillet(4.0)
    s = s.cut(box(ix0, iy0, FLOOR, ix1, iy1, CEILING))
    # Hanging from the ceiling: screw columns, button guides, pinhole guides, bosses for the pedestal.
    for x, y in HOLES:
        s = s.union(cyl(x, y, BOARD, CEILING, 3.0))
    for (x, y, r) in lay["buttons"]:
        s = s.union(cyl(x, y, CEILING - TUBE, CEILING, r + 1.6))
    pins = [(PROMAX_X0 + 6.4, 62.3), (PROMAX_X0 + 14.6, 62.3)]   # BOOT and RESET; reach them with a paper clip
    for x, y in pins:
        s = s.union(cyl(x, y, PROMAX_Z + 5.5, CEILING, 2.6))
    for dx, dy in PED_SCREWS:
        s = s.union(cyl(PAN_X + dx, PAN_Y + dy, CEILING - 6, CEILING, 3.0))
    for x, y in HOLES:
        s = s.cut(cyl(x, y, BOARD, BOARD + 10, 1.05))
    for (x, y, r) in lay["buttons"]:
        s = s.cut(cyl(x, y, CEILING - TUBE, TOP, r))
    for x, y in pins:
        s = s.cut(cyl(x, y, PROMAX_Z + 5.5, TOP, 1.0))
    for dx, dy in PED_SCREWS:
        s = s.cut(cyl(PAN_X + dx, PAN_Y + dy, CEILING - 6, TOP, 1.05))
    # Side A: Ethernet, barrel jack (a notch open downwards, so the shell lifts off), battery terminal.
    s = s.cut(box(PROMAX_X0 + 1.9, iy0 - WALL, PROMAX_Z + 0.6, PROMAX_X0 + 19.0, iy0, PROMAX_Z + 1.6 + RJ45_TOP))
    s = s.cut(box(JACK_X - JACK_W / 2 - 0.4, iy0 - WALL, FLOOR, JACK_X + JACK_W / 2 + 0.4, iy0, BOARD + JACK_H + 0.4))
    s = s.cut(box(TERMINAL_X - 5.4, iy0 - WALL, BOARD, TERMINAL_X + 5.4, iy0, BOARD + 10.4))
    # Side C: Type-C, card slot in a thumb scoop, three status lights.
    s = s.cut(box(PROMAX_X0 + 4.2, iy1, PROMAX_Z - 1.4, PROMAX_X0 + 16.8, iy1 + WALL, PROMAX_Z + 5.4))
    card = (lay["card"][0] + lay["card"][1]) / 2
    s = s.cut(box(lay["card"][0], iy1, BOARD + 0.3, lay["card"][1], iy1 + WALL, BOARD + 2.6))
    s = s.cut(cyly(card, iy1 + 1.0, iy1 + WALL, BOARD + 1.4, 7.0))
    for x in lay["lights"]:
        s = s.cut(cyly(x, iy1, iy1 + WALL, BOARD + 2.0, 1.6))   # bent 3 mm LED
    # Side D: grille for the temperature and humidity sensor, low and near side C.
    for i in range(5):
        s = s.cut(box(ix0 - WALL, 46 + i * 4.5, BOARD + 1, ix0, 48 + i * 4.5, BOARD + 9))
    # Roof: pan servo, cable hole, system light, SoC grille.
    f = SERVO_FIT + 0.1
    s = s.cut(box(PAN_X - SERVO_W / 2 - f, PAN_Y - SERVO_SHAFT - f, CEILING,
                  PAN_X + SERVO_W / 2 + f, PAN_Y + SERVO_L - SERVO_SHAFT + f, TOP))
    s = s.cut(box(PAN_X + CABLE[0], PAN_Y + CABLE[1], CEILING, PAN_X + CABLE[2], PAN_Y + CABLE[3], TOP))
    s = s.cut(cyl(PROMAX_X0 + 4.1, 70.2, CEILING, TOP, 1.2)).cut(cyl(PROMAX_X0 + 16.9, 70.2, CEILING, TOP, 1.2))
    for i in range(5):
        s = s.cut(box(PROMAX_X0 + 3, 34 + i * 3.2, CEILING, PROMAX_X0 + 18, 35.6 + i * 3.2, TOP))
    return s


def pedestal():
    """Stands on the roof around the pan servo; the yoke turns on its rim."""
    f = SERVO_FIT
    seat = RING_H - SERVO_UP     # underside of the servo's tabs above the roof
    p = cyl(0, 0, 0, RING_H, RING_R).cut(cyl(0, 0, RING_FLOOR, RING_H, RING_R - RING_WALL))
    # Two posts under the servo's tabs.
    p = p.union(box(-SERVO_W / 2, SERVO_L - SERVO_SHAFT + f, RING_FLOOR,
                    SERVO_W / 2, SERVO_L - SERVO_SHAFT + 5.0, seat))
    p = p.union(box(-SERVO_W / 2, -SERVO_SHAFT - 5.0, RING_FLOOR, SERVO_W / 2, -SERVO_SHAFT - f, seat))
    mid = SERVO_L / 2 - SERVO_SHAFT
    for y in (mid - SERVO_HOLES / 2, mid + SERVO_HOLES / 2):
        p = p.cut(cyl(0, y, seat - 8, seat, 0.75))
    p = p.cut(box(-SERVO_W / 2 - f, -SERVO_SHAFT - f, 0, SERVO_W / 2 + f, SERVO_L - SERVO_SHAFT + f, RING_FLOOR))
    p = p.cut(box(CABLE[0], CABLE[1], 0, CABLE[2], CABLE[3], RING_FLOOR))
    for dx, dy in PED_SCREWS:
        p = p.cut(cyl(dx, dy, 0, RING_FLOOR, 1.45))
    # Stop at the back of the rim; the groove under the yoke lets it turn 94 degrees each way.
    stop = cyl(0, 0, RING_H, RING_H + 1.9, RING_R).cut(cyl(0, 0, RING_H, RING_H + 1.9, RING_R - RING_WALL))
    p = p.union(stop.intersect(sector(266, 274, RING_R + 1, RING_H, RING_H + 1.9)))
    return at_pan(p, TOP)


def yoke():
    """Turns on the pedestal, clamped to the servo by its horn; one arm carries the tilt servo, the other a pivot."""
    t, f = YOKE_T, SERVO_FIT
    axis = t + TILT_Z
    y = cyl(0, 0, 0, t, RING_R + 2.0).union(box(-ARM_IN - ARM_T, -9, 0, ARM_IN + ARM_SERVO_T, 9, t))
    # The horn disc sits in a pocket underneath; two M2 x 5 screws from above pull the plate onto it,
    # and the hole in the middle reaches the screw that holds the disc on the shaft.
    y = y.cut(cyl(0, 0, 0, DISC_UP - 0.4, DISC_D / 2 + 0.3)).cut(cyl(0, 0, 0, t, 2.6))
    for x in (-DISC_HOLES / 2, DISC_HOLES / 2):
        y = y.cut(cyl(x, 0, 0, t, 1.3))
    y = y.cut(box(CABLE[0], CABLE[1], 0, CABLE[2], CABLE[3], t))
    groove = cyl(0, 0, 0, 2.3, RING_R + 0.4).cut(cyl(0, 0, 0, 2.3, RING_R - RING_WALL - 0.4))
    y = y.cut(groove.intersect(sector(176, 364, RING_R + 2, 0, 2.3)))
    # Pivot arm on the side D side, with a pin that the head's halves close around.
    y = y.union(box(-ARM_IN - ARM_T, -9, t, -ARM_IN, 9, axis + 9))
    y = y.union(cylx(-ARM_IN, -ARM_IN + 5.0, 0, axis, 3.0))
    # Servo arm: the servo goes in from outside, long end down, tabs against the outer face.
    x0, x1 = ARM_IN, ARM_IN + ARM_SERVO_T
    y = y.union(box(x0, -9, t, x1, 9, axis + 11))
    y = y.cut(box(x0, -SERVO_W / 2 - f, axis - (SERVO_L - SERVO_SHAFT) - f, x1, SERVO_W / 2 + f, axis + SERVO_SHAFT + f))
    mid = SERVO_SHAFT - SERVO_L / 2
    for z in (mid - SERVO_HOLES / 2, mid + SERVO_HOLES / 2):
        y = y.cut(cylx(x0, x1, 0, axis + z, 0.75))
    return at_pan(y, YOKE_Z)


def head():
    """Housing for the camera below and the OLED above, looking towards side C; head coordinates."""
    t = HEAD_WALL
    front, top, half = HEAD_D / 2, HEAD_H / 2, HEAD_W / 2
    h = box(-half, -front, -top, half, front, top)
    h = h.union(box(-half, front - SLAB_D, top, half, front, top + SLAB_H))
    try:
        h = h.edges().fillet(1.5)
    except Exception:
        pass
    h = h.cut(box(-half + t, -front + t, -top + t, half - t, front - t, top - t))
    h = h.cut(box(-half + t, front - SLAB_D + t, top - t, half - t, front - t, top + SLAB_H - t))
    h = h.cut(cyly(0, front - t - 0.5, front + 0.5, CAM_Z, CAM_LENS / 2 + 0.4))
    w, hh, off = OLED_AA
    h = h.cut(box(-w / 2 - 0.5, front - t - 0.5, OLED_TOP - off - hh - 0.5, w / 2 + 0.5, front + 0.5, OLED_TOP - off + 0.5))
    # Posts for the four screws that join the halves, from the back.
    for x, z in POSTS:
        h = h.union(box(x - 2.5, -front + t, z - 2.3, x + 2.5, front - t, z + 2.3))
    for x, z in POSTS:
        h = h.cut(cyly(x, 0, 8, z, 0.8)).cut(cyly(x, -front + t, 0, z, 1.2)).cut(cyly(x, -front, -3, z, 2.2))
    # Camera board on four posts from the back wall, M2 screws from the lens side.
    back = front - CAM_DEPTH - 1.2
    cam_top = CAM_Z + CAM_AXIS
    for x in (-10.5, 10.5):
        for z in (cam_top - 2.0, cam_top - 15.5):
            h = h.union(cyly(x, -front + t, back, z, 2.2)).cut(cyly(x, -front + t + 0.6, back, z, 0.8))
    h = h.cut(box(-7, -front + t, -top, 7, -front + t + 3.5, -top + t))     # cables leave through the floor
    # Side B wall: the tilt servo's horn disc sits in a round opening. Two M2 cap screws stand in the
    # disc, above and below the shaft; the halves close around their heads and the head turns with them.
    face = half + 1.0 - DISC_UP                  # the disc's face away from the servo
    h = h.union(box(face - 2.5, -6, -11, half - t, 6, 11))
    h = h.cut(cylx(face, half, 0, 0, DISC_D / 2 + 0.4)).cut(cylx(face - 2.5, face, 0, 0, 2.8))
    for z in (-DISC_HOLES / 2, DISC_HOLES / 2):
        h = h.cut(box(face - 2.3, -2.1, z - 2.4, face, 2.1, z + 2.4))
    # Side D wall: bearing for the yoke's pivot pin.
    h = h.union(box(-half + t, -5.5, -5.5, -half + 5.0, 5.5, 5.5)).cut(cylx(-half, -half + 5.0, 0, 0, 3.2))
    return h


def head_halves():
    big = 100
    front = head().intersect(box(-big, 0, -big, big, big, big))
    back = head().intersect(box(-big, -big, -big, big, 0, big))
    at = (PAN_X, PAN_Y, HEAD_Z)
    return front.translate(at), back.translate(at)


def cap(x, y, r, power):
    """Button cap: rides in the roof's guide tube, rests on the switch, sits 1 mm below the roof."""
    stem = r - 0.3
    rest = BOARD + (LATCH_TOP if power else SWITCH_TOP)     # where the cap meets the switch
    low = rest - (3.0 if power else 0.8)
    stop = CEILING - TUBE - 0.5                             # top of the flange that keeps the cap in
    c = cyl(0, 0, low, TOP - 1.0, stem)
    cone = cq.Workplane("XY").circle(r + 1.0).workplane(offset=stop - (stop - 1.3)).circle(stem).loft()
    c = c.union(cyl(0, 0, stop - 2.3, stop - 1.3, r + 1.0)).union(cone.translate((0, 0, stop - 1.3)))
    if power:
        c = c.cut(box(-LATCH_STEM / 2 - 0.15, -LATCH_STEM / 2 - 0.15, low, LATCH_STEM / 2 + 0.15, LATCH_STEM / 2 + 0.15, rest))
    else:
        c = c.cut(cyl(0, 0, low, rest, 1.95))
    return c.translate((x, y, 0))


def look_down():
    """How far the camera can tilt down, per heading, before the base enters the bottom of the picture."""
    lens_h = HEAD_Z + CAM_Z - TOP
    x0, y0, x1, y1 = outline()
    out = []
    for name, deg in [("C", 90), ("C-D", 135), ("D", 180), ("D-A", 225), ("A", 270), ("A-B", 315), ("B", 0), ("B-C", 45)]:
        dx, dy = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        reach = min(((x1 if dx > 0 else x0) - PAN_X) / dx if abs(dx) > 1e-6 else 1e9,
                    ((y1 if dy > 0 else y0) - PAN_Y) / dy if abs(dy) > 1e-6 else 1e9)
        ahead = max(reach - HEAD_D / 2, 0.1)   # base still in front of the lens tip
        out.append("%s %d" % (name, round(math.degrees(math.atan(lens_h / ahead)) - 22)))  # 22: half the vertical view
    return "lens %.0f mm above the roof; clear tilt down, degrees, towards side: %s" % (lens_h, ", ".join(out))


PRINTED = ["base_bottom", "base_shell", "pedestal", "yoke", "head_front", "head_back", "cap_power", "cap_net", "cap_stop"]
# Pairs that touch by design and must not overlap.
CLEAR = [("base_shell", "baseboard"), ("base_shell", "promax"), ("base_shell", "pan_servo"), ("base_shell", "base_bottom"),
         ("base_shell", "cap_power"), ("base_shell", "cap_net"), ("base_shell", "cap_stop"),
         ("cap_power", "baseboard"), ("cap_net", "baseboard"), ("cap_stop", "baseboard"),
         ("pedestal", "pan_servo"), ("pedestal", "base_shell"), ("pedestal", "yoke"), ("yoke", "pan_servo"),
         ("yoke", "tilt_servo"), ("yoke", "head_front"), ("yoke", "head_back"), ("head_front", "head_back"),
         ("head_front", "camera"), ("head_back", "camera"), ("head_front", "oled"), ("head_back", "tilt_servo"),
         ("base_bottom", "baseboard"), ("pan_servo", "baseboard")]


def main():
    print(look_down())
    front, back = head_halves()
    b = LAYOUTS[LAYOUT]["buttons"]
    parts = {"base_bottom": base_bottom(), "base_shell": base_shell(), "pedestal": pedestal(), "yoke": yoke(),
             "head_front": front, "head_back": back,
             "cap_power": cap(*b[0], True), "cap_net": cap(*b[1], False), "cap_stop": cap(*b[2], False)}
    parts.update(references())
    out = os.path.join(HERE, "out", LAYOUT)
    os.makedirs(out, exist_ok=True)
    asm = cq.Assembly()
    colours = {"base_bottom": "gray30", "base_shell": "gray80", "pedestal": "gray65", "yoke": "gray55",
               "head_front": "gray80", "head_back": "gray70", "cap_power": "red3", "cap_net": "gray30", "cap_stop": "gray30",
               "baseboard": "darkgreen", "promax": "black", "pan_servo": "blue3", "tilt_servo": "blue3",
               "camera": "darkgreen", "oled": "blue3"}
    for name, shape in parts.items():
        cq.exporters.export(shape, os.path.join(out, name + ".step"))
        if name in PRINTED:
            cq.exporters.export(shape, os.path.join(out, name + ".stl"))
        asm.add(shape, name=name, color=cq.Color(colours[name]))
    asm.save(os.path.join(out, "assembly.step"))
    for a, c in CLEAR:
        v = parts[a].intersect(parts[c]).val().Volume()
        if v > 0.5:
            print("OVERLAP %s / %s: %.1f mm3" % (a, c, v))
    x0, y0, x1, y1 = outline()
    print("height %.1f mm, footprint %.1f x %.1f mm" % (HEAD_Z + HEAD_H / 2 + SLAB_H, x1 - x0, y1 - y0))


if __name__ == "__main__":
    main()
