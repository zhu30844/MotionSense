#!/usr/bin/env python3
"""Base and pan-tilt head for the Pro Max baseboard. Needs CadQuery; writes STEP and STL to out/.

Axes: x runs from side D to side B, y from side A (back: Ethernet, power) to side C (front),
z up from the desk. The origin is the baseboard's corner at sides D and A, on the desk.
"""
import os
import sys

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))

# Where the buttons, card slot and lights sit; pick one on the command line.
# buttons: power, network, safe stop as (x, y, hole radius); card: slot x range; lights: x of each.
# pan: where the pan axis stands.
LAYOUTS = {
    "middle": {"buttons": [(67, 12, 5.2), (67, 30, 3.8), (67, 44, 3.8)], "card": (52, 65), "lights": (20, 28, 36),
               "pan": (32, 36)},
    "front": {"buttons": [(46, 65, 5.2), (57, 65, 3.8), (67, 65, 3.8)], "card": (6, 19), "lights": (26, 33, 40),
              "pan": (32, 36)},
    # Pan axis in the corner of sides D and C, so the head looks down past two near edges.
    # Buttons in a column beside the Pro Max, clear of the turntable.
    "corner": {"buttons": [(67, 12, 5.2), (67, 30, 3.8), (67, 44, 3.8)], "card": (52, 65), "lights": (20, 28, 36),
               "pan": (27, 49)},
}
LAYOUT = sys.argv[1] if len(sys.argv) > 1 else "corner"

# ---- Baseboard and what stands on it --------------------------------------
PCB_X, PCB_Y, PCB_T = 100.0, 72.0, 1.6
PROMAX_X0 = 77.0        # left edge of the Pro Max; it is 21 wide and as long as the baseboard
SOCKET_H = 11.0         # baseboard top to Pro Max underside, on 8.5 mm sockets
RJ45_TOP = 13.4         # above the Pro Max top face

# ---- Base ------------------------------------------------------------------
WALL, FLOOR, ROOF = 2.4, 2.4, 2.4
STANDOFF = 4.0
GAP_X, GAP_Y = 0.6, 1.4  # cavity past the board; in y this also covers the connector overhang
PCB_Z = FLOOR + STANDOFF
PROMAX_Z = PCB_Z + PCB_T + SOCKET_H
CEILING = PROMAX_Z + 1.0 + RJ45_TOP + 1.0
TOP = CEILING + ROOF

# ---- Servo: EMAX ES08MA II, from its drawing --------------------------------
SERVO_L, SERVO_W, SERVO_H = 23.0, 11.5, 24.0
SERVO_TAB_Z, SERVO_TAB_T, SERVO_TAB_L = 15.0, 2.5, 32.5
SERVO_HOLES = 27.6
SERVO_SHAFT = 5.75      # shaft axis from the near end of the body; measure on the part
SERVO_FIT = 0.3

# ---- Pan-tilt ----------------------------------------------------------------
PAN_X, PAN_Y = LAYOUTS[LAYOUT]["pan"]
RING_R, RING_H = 24.0, 20.0  # turntable ring on the roof; the yoke rides on it. Tall, to look down from a fridge top
YOKE_T = 3.0
HEAD_W, HEAD_D, HEAD_H = 36.0, 30.0, 32.0   # camera block; the tilt axis runs through its centre
SLAB_D, SLAB_H = 8.0, 32.0                  # thin upper part for the OLED, flush with the front
ARM_T = 4.0
TILT_Z = HEAD_H / 2 + 8.0    # tilt axis above the yoke plate; the block's corners swing 22 mm

# ---- Camera (SC3336 B) and OLED module, from their drawings ------------------
CAM_W, CAM_H, CAM_LENS = 25.0, 24.0, 14.0
CAM_AXIS = 8.5               # lens axis below the board's top edge
OLED_W, OLED_H = 27.3, 27.8
OLED_AA = (21.74, 10.86, 6.37)  # active area: width, height, top edge below the board top

# ---- Head interior, in head coordinates (origin on the tilt axis) -------------
HEAD_WALL = 2.0
HEAD_Z = TOP + RING_H + 0.4 + YOKE_T + TILT_Z
CAM_Z = -HEAD_H / 2 + 4 + CAM_H - CAM_AXIS   # lens axis
OLED_TOP = HEAD_H / 2 + SLAB_H - 2.1         # top edge of the OLED board


def box(x0, y0, z0, x1, y1, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def cyl(x, y, z0, z1, r):
    return cq.Workplane("XY").circle(r).extrude(z1 - z0).translate((x, y, z0))


def servo(shaft_up=True):
    """Servo with its shaft axis on the z axis and the tab underside at z = 0."""
    s = box(-SERVO_SHAFT, -SERVO_W / 2, -SERVO_TAB_Z, SERVO_L - SERVO_SHAFT, SERVO_W / 2, SERVO_H - SERVO_TAB_Z)
    c = SERVO_L / 2 - SERVO_SHAFT
    s = s.union(box(c - SERVO_TAB_L / 2, -SERVO_W / 2, 0, c + SERVO_TAB_L / 2, SERVO_W / 2, SERVO_TAB_T))
    return s.union(cyl(0, 0, SERVO_H - SERVO_TAB_Z, SERVO_H - SERVO_TAB_Z + 4.0, 2.4))


def references():
    """Bought parts, for checking fit; not printed."""
    pcb = box(0, 0, PCB_Z, PCB_X, PCB_Y, PCB_Z + PCB_T)
    pm = box(PROMAX_X0, 0, PROMAX_Z, PROMAX_X0 + 21, PCB_Y, PROMAX_Z + 1.0)
    pm = pm.union(box(PROMAX_X0 + 2.4, -1.25, PROMAX_Z + 1, PROMAX_X0 + 18.5, 20.4, PROMAX_Z + 1 + RJ45_TOP))
    pm = pm.union(box(PROMAX_X0 + 5.7, 65.6, PROMAX_Z + 0.1, PROMAX_X0 + 15.3, 73.3, PROMAX_Z + 4.25))
    pm = pm.union(box(PROMAX_X0 + 1.6 - 1.3, 21, PCB_Z + PCB_T, PROMAX_X0 + 1.6 + 1.3, 72, PROMAX_Z))
    pm = pm.union(box(PROMAX_X0 + 19.4 - 1.3, 21, PCB_Z + PCB_T, PROMAX_X0 + 19.4 + 1.3, 72, PROMAX_Z))
    pan = servo().translate((PAN_X, PAN_Y, CEILING - SERVO_TAB_T))
    at = (PAN_X, PAN_Y, HEAD_Z)
    return {"baseboard": pcb, "promax": pm, "pan_servo": pan,
            "camera": camera().translate(at), "oled": oled().translate(at)}


def camera():
    """SC3336 module in head coordinates: lens tip flush with the front face."""
    front = HEAD_D / 2
    back = front - 23.95                  # front face of the camera board
    top = CAM_Z + CAM_AXIS                # top edge of the camera board
    c = box(-CAM_W / 2, back - 1.2, top - CAM_H, CAM_W / 2, back, top)
    c = c.union(box(-7.1, back - 3.2, top - CAM_H, 7.1, back - 1.2, top - CAM_H + 5))      # cable socket
    c = c.union(box(-7, back, CAM_Z - 7, 7, back + 10, CAM_Z + 7))                         # lens holder
    return c.union(cq.Workplane("XZ").circle(CAM_LENS / 2).extrude(-(23.95 - 10)).translate((0, back + 10, CAM_Z)))


def oled():
    """OLED module in head coordinates: glass against the inside of the front wall."""
    inside = HEAD_D / 2 - HEAD_WALL
    o = box(-OLED_W / 2, inside - 2.6, OLED_TOP - OLED_H, OLED_W / 2, inside - 1.4, OLED_TOP)
    return o.union(box(-26.7 / 2, inside - 1.4, OLED_TOP - 4.27 - 19.26, 26.7 / 2, inside, OLED_TOP - 4.27))


def base_bottom():
    """Floor plate with the board standoffs; the shell drops over it."""
    x0, y0, x1, y1 = -GAP_X - WALL, -GAP_Y - WALL, PCB_X + GAP_X + WALL, PCB_Y + GAP_Y + WALL
    p = box(x0, y0, 0, x1, y1, FLOOR)
    for x, y in [(4, 4), (4, PCB_Y - 4), (PCB_X - 28, 4), (PCB_X - 28, PCB_Y - 4)]:
        p = p.union(cyl(x, y, FLOOR, PCB_Z, 3.2)).cut(cyl(x, y, 0, PCB_Z, 1.3))
    return p


def base_shell():
    """Walls and roof in one piece, with every opening."""
    ix0, iy0, ix1, iy1 = -GAP_X, -GAP_Y, PCB_X + GAP_X, PCB_Y + GAP_Y
    s = box(ix0 - WALL, iy0 - WALL, FLOOR, ix1 + WALL, iy1 + WALL, TOP).edges("|Z").fillet(4.0)
    s = s.cut(box(ix0, iy0, FLOOR, ix1, iy1, CEILING))
    top = PCB_Z + PCB_T
    # Side A: Ethernet, barrel jack, battery terminal.
    s = s.cut(box(PROMAX_X0 + 1.9, iy0 - WALL, PROMAX_Z + 0.6, PROMAX_X0 + 19.0, iy0, PROMAX_Z + 1.6 + RJ45_TOP))
    s = s.cut(box(14, iy0 - WALL, top, 24, iy0, top + 11.5))
    s = s.cut(box(32, iy0 - WALL, top + 1.5, 44, iy0, top + 9))
    # Side C: Type-C, card slot, three status lights.
    s = s.cut(box(PROMAX_X0 + 4.2, iy1, PROMAX_Z - 1.4, PROMAX_X0 + 16.8, iy1 + WALL, PROMAX_Z + 5.4))
    lay = LAYOUTS[LAYOUT]
    s = s.cut(box(lay["card"][0], iy1, top + 0.3, lay["card"][1], iy1 + WALL, top + 2.6))
    for x in lay["lights"]:
        s = s.cut(cq.Workplane("XZ").circle(1.1).extrude(-WALL).translate((x, iy1, top + 1.5)))
    # Side D: grille for the temperature and humidity sensor, low and near side C.
    for i in range(5):
        s = s.cut(box(ix0 - WALL, 46 + i * 4.5, top + 1, ix0, 48 + i * 4.5, top + 9))
    # Roof: pan servo, cable slot, turntable ring, buttons, pinholes, light hole, SoC grille.
    c = PAN_X + SERVO_L / 2 - SERVO_SHAFT
    s = s.cut(box(c - SERVO_L / 2 - SERVO_FIT, PAN_Y - SERVO_W / 2 - SERVO_FIT, CEILING,
                  c + SERVO_L / 2 + SERVO_FIT, PAN_Y + SERVO_W / 2 + SERVO_FIT, TOP))
    for dx in (-SERVO_HOLES / 2, SERVO_HOLES / 2):
        s = s.cut(cyl(c + dx, PAN_Y, CEILING, TOP, 1.0))
    s = s.union(cyl(PAN_X, PAN_Y, TOP, TOP + RING_H, RING_R).cut(cyl(PAN_X, PAN_Y, TOP, TOP + RING_H, RING_R - 2.4)))
    s = s.cut(box(PAN_X - 6, PAN_Y + 9, CEILING, PAN_X + 6, PAN_Y + 12.5, TOP))
    for (x, y, r) in lay["buttons"]:
        s = s.cut(cyl(x, y, CEILING, TOP, r))
    for x in (PROMAX_X0 + 6.4, PROMAX_X0 + 14.6):
        s = s.cut(cyl(x, 62.3, CEILING, TOP, 0.9))
    s = s.cut(cyl(PROMAX_X0 + 4.1, 70.2, CEILING, TOP, 1.2)).cut(cyl(PROMAX_X0 + 16.9, 70.2, CEILING, TOP, 1.2))
    for i in range(5):
        s = s.cut(box(PROMAX_X0 + 3, 34 + i * 3.2, CEILING, PROMAX_X0 + 18, 35.6 + i * 3.2, TOP))
    return s


def yoke():
    """Turns on the ring; carries the tilt servo on one arm and a pivot on the other."""
    z = TOP + RING_H + 0.4
    y = cyl(PAN_X, PAN_Y, z, z + YOKE_T, RING_R + 1.0)
    half = HEAD_W / 2 + 1.0
    for side in (-1, 1):
        x0 = PAN_X + side * half
        arm = box(min(x0, x0 + side * ARM_T), PAN_Y - 9, z, max(x0, x0 + side * ARM_T), PAN_Y + 9, z + YOKE_T + TILT_Z + 9)
        y = y.union(arm)
    y = y.cut(cq.Workplane("YZ").circle(2.6).extrude(HEAD_W + 2 * ARM_T + 4).translate(
        (PAN_X - half - ARM_T - 1, PAN_Y, z + YOKE_T + TILT_Z)))
    return y.cut(box(PAN_X - 6, PAN_Y + 9, z, PAN_X + 6, PAN_Y + 12.5, z + YOKE_T))


def head():
    """Housing for the camera below and the OLED above, looking towards side C."""
    t = HEAD_WALL
    front, top = HEAD_D / 2, HEAD_H / 2
    h = box(-HEAD_W / 2, -HEAD_D / 2, -top, HEAD_W / 2, front, top)
    h = h.union(box(-HEAD_W / 2, front - SLAB_D, top, HEAD_W / 2, front, top + SLAB_H)).edges().fillet(1.5)
    h = h.cut(box(-HEAD_W / 2 + t, -HEAD_D / 2 + t, -top + t, HEAD_W / 2 - t, front - t, top - t))
    h = h.cut(box(-HEAD_W / 2 + t, front - SLAB_D + t, top - t, HEAD_W / 2 - t, front - t, top + SLAB_H - t))
    h = h.cut(cq.Workplane("XZ").circle(CAM_LENS / 2 + 0.4).extrude(-4).translate((0, front - 3.5, CAM_Z)))
    w, hh, off = OLED_AA
    h = h.cut(box(-w / 2 - 0.5, front - 2.5, OLED_TOP - off - hh - 0.5, w / 2 + 0.5, front + 0.5, OLED_TOP - off + 0.5))
    return h.translate((PAN_X, PAN_Y, HEAD_Z))


def look_down():
    """How far the camera can tilt down, per heading, before the base enters the bottom of the picture."""
    import math
    lens_h = HEAD_Z + CAM_Z - TOP
    x0, y0, x1, y1 = -GAP_X - WALL, -GAP_Y - WALL, PCB_X + GAP_X + WALL, PCB_Y + GAP_Y + WALL
    out = []
    for name, deg in [("C", 90), ("C-D", 135), ("D", 180), ("D-A", 225), ("A", 270), ("A-B", 315), ("B", 0), ("B-C", 45)]:
        dx, dy = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        reach = min(((x1 if dx > 0 else x0) - PAN_X) / dx if abs(dx) > 1e-6 else 1e9,
                    ((y1 if dy > 0 else y0) - PAN_Y) / dy if abs(dy) > 1e-6 else 1e9)
        ahead = max(reach - HEAD_D / 2, 0.1)   # base still in front of the lens tip
        out.append("%s %d" % (name, round(math.degrees(math.atan(lens_h / ahead)) - 22)))  # 22: half the vertical view
    return "lens %.0f mm above the roof; clear tilt down, degrees, towards side: %s" % (lens_h, ", ".join(out))


def main():
    print(look_down())
    parts = {"base_bottom": base_bottom(), "base_shell": base_shell(), "yoke": yoke(), "head": head()}
    parts.update(references())
    out = os.path.join(HERE, "out", LAYOUT)
    os.makedirs(out, exist_ok=True)
    asm = cq.Assembly()
    colours = {"base_bottom": "gray30", "base_shell": "gray80", "yoke": "gray55", "head": "gray80",
               "baseboard": "darkgreen", "promax": "black", "pan_servo": "blue3",
               "camera": "darkgreen", "oled": "blue3"}
    for name, shape in parts.items():
        cq.exporters.export(shape, os.path.join(out, name + ".step"))
        if name in ("base_bottom", "base_shell", "yoke", "head"):
            cq.exporters.export(shape, os.path.join(out, name + ".stl"))
        asm.add(shape, name=name, color=cq.Color(colours[name]))
    asm.save(os.path.join(out, "assembly.step"))
    print("height %.1f mm, footprint %.1f x %.1f mm" % (
        HEAD_Z + HEAD_H / 2 + SLAB_H,
        PCB_X + 2 * (GAP_X + WALL), PCB_Y + 2 * (GAP_Y + WALL)))


if __name__ == "__main__":
    main()
