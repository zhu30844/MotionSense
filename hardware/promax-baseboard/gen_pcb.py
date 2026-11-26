#!/usr/bin/env python3
"""Writes baseboard.kicad_pcb: outline, every part in its place, nets, no tracks yet.

Needs KiCad's pcbnew module and kicad-cli. Positions are in the enclosure model's axes
(hardware/enclosure/model.py): x from side D to side B, y from side A (back) to side C (front),
origin at the board's corner of sides D and A. On screen the front is at the top.
Rotations are counter-clockwise as seen from above.
"""
import os
import re
import subprocess
import tempfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = "baseboard"
FPDIR = "/usr/share/kicad/footprints"
PCB_X, PCB_Y = 100.0, 72.0
OX, OY = 100.0, 60.0    # where the board sits on the KiCad sheet

# Pro Max, from its STEP model: 21 wide, rows 1.62 in from the long edges, pins 22.38-70.64 from the Ethernet end.
PROMAX_X0 = 77.0
ROW_1, ROW_21 = PROMAX_X0 + 1.62, PROMAX_X0 + 21 - 1.62
PIN_Y0, PIN_Y1 = 22.38, 70.64


def pin_y(n):
    """y of header pin n (1-40); pins 1 and 40 are at the Type-C end."""
    return PIN_Y1 - (n - 1) * 2.54 if n <= 20 else PIN_Y0 + (n - 21) * 2.54


# ref: (x, y, rotation, anchor). The anchor is the middle of the pads unless it says "origin".
PLACE = {
    # Pro Max sockets.
    "J3": (ROW_1, (PIN_Y0 + PIN_Y1) / 2, 90), "J4": (ROW_21, (PIN_Y0 + PIN_Y1) / 2, 270),
    # Side A: barrel jack (axis x = 19, face 3.5 mm past the edge, flush with the outer wall) and battery terminal.
    "J1": (21.3, 7.1, 90, "origin"), "J2": (38, 4.2, 0),
    "D1": (21.5, 18, 180), "D7": (38, 15, 0), "F1": (29.2, 17.5, 90), "D2": (29.1, 8, 90), "C1": (38.5, 22.5, 0),
    # Buttons on the roof column x = 67 of layout "corner".
    "SW1": (67, 12, 0), "SW2": (67, 30, 0), "SW3": (67, 44, 0),
    "R3": (67, 19.5, 0), "R4": (67, 21.7, 0),
    "R54": (60, 31.2, 0), "C50": (60, 28.9, 0), "R55": (60, 45.2, 0), "C51": (60, 42.9, 0),
    # Side D: coin cell, RTC, then the sensor behind the grille.
    "BT1": (9.5, 27.5, 90, "origin"), "U4": (8.5, 44.5, 0), "C40": (8.5, 51.2, 0),
    "U6": (2.2, 57, 0), "C42": (5.6, 57, 90),
    # Side C, left to right: lights, head and servo plugs below the cable slot, card slot.
    # The lights are bent 3 mm LEDs; their tips stop 0.2 mm short of the wall.
    "D4": (20, 66.5, 180), "D5": (28, 66.5, 180), "D6": (36, 66.5, 180),
    "R31": (24, 69, 90), "R32": (32, 69, 90), "R33": (40, 69, 90),
    "J5": (22, 61.5, 0), "R50": (11, 62.5, 0), "R51": (11, 64.7, 0),
    "J6": (35.5, 58.5, 90), "J7": (35.5, 62.6, 90), "R52": (43, 58.5, 180), "R53": (43, 62.6, 180),
    "C26": (49.5, 48.5, 90),
    "J10": (58.5, 63, 180, "origin"), "C60": (47.9, 58, 0), "C61": (47.9, 61, 0),
    "R66": (55.5, 51.9, 90), "R67": (57.6, 51.9, 90), "R68": (59.7, 51.9, 90), "R69": (61.8, 51.9, 90),
    "R70": (63.9, 51.9, 90), "R71": (66, 51.9, 90),
    # Between the button column and the Pro Max: serial headers and I2C test points.
    "J9": (74.3, 27, 0), "J8": (74.3, 58, 0), "TP1": (74.2, 46.5, 0), "TP2": (74.2, 50.3, 0),
    # Under the Pro Max, each next to its header pin.
    "R65": (92.3, pin_y(21), 180), "R64": (92.3, pin_y(22), 180), "R63": (92.3, pin_y(24), 180),
    "R62": (92.3, pin_y(25), 180), "R60": (92.3, pin_y(26), 180), "R61": (92.3, pin_y(27), 180),
    "R40": (83, pin_y(16), 0), "R42": (83, pin_y(10), 0), "R41": (83, pin_y(9), 0),
    "R1": (92.3, 48, 0), "R2": (92.3, pin_y(32), 180), "C2": (92.3, 52.6, 180),
    "U5": (84, 56, 0), "C41": (84, 53, 0),
    "U3": (88.5, 62.5, 0), "C30": (88.5, 65.3, 0), "C31": (88.5, 59.7, 0), "R30": (92.6, 61.5, 90),
    "D3": (86, 68.6, 180),
}


def buck(n, x, y, first):
    """TPS54302 stage around its chip at (x, y); offsets are as seen on screen, y down."""
    c, r = "C%d", "R%d"
    for ref, dx, dy, rot in [("U%d" % n, 0, 0, 0), (c % first, -4.2, 0, 90), (c % (first + 1), -6.5, 0, 90),
                             (c % (first + 2), 4.2, -1.7, 0), ("L%d" % n, -1.6, 6.0, 0),
                             (r % (first + 1), 3.4, 2.3, 270), (r % first, 5.5, 2.3, 90), (c % (first + 5), 7.6, 2.3, 90),
                             (c % (first + 3), 6.2, 5.6, 0), (c % (first + 4), 6.2, 8.1, 0)]:
        PLACE[ref] = (x + dx, y - dy, rot)


buck(1, 51.3, 10.8, 10)
buck(2, 51.3, 24.3, 20)
PLACE.update({"R22": (51.3 + 9.7, 24.3 - 2.0, 270), "JP1": (51.3 + 10.5, 24.3 - 5.8, 270)})

HOLES = [(4, 4), (4, 68), (72, 4), (72, 68)]

# What the enclosure puts over the board, drawn on Dwgs.User: (label, x0, y0, x1, y1).
OVERHEAD = [
    ("PRO MAX 11 mm up", PROMAX_X0, 0, PROMAX_X0 + 21, 72),
    ("RJ45", PROMAX_X0 + 2.4, -1.25, PROMAX_X0 + 18.5, 20.4),
    ("PAN SERVO 8.9 mm up", 21.25, 43.25, 44.25, 54.75),
    ("CABLE SLOT", 21, 58, 33, 61.5),
]
SENSOR_GRILLE = (46, 66)   # y range on side D


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + PCB_Y - y))


def tokens(text):
    return re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text)


def parse(toks, i=0):
    """S-expression to nested lists; strings lose their quotes."""
    out = []
    while i < len(toks):
        t = toks[i]
        if t == "(":
            sub, i = parse(toks, i + 1)
            out.append(sub)
        elif t == ")":
            return out, i + 1
        else:
            out.append(t[1:-1] if t.startswith('"') else t)
            i += 1
    return out, i


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def one(node, key):
    f = find(node, key)
    return f[0][1] if f and len(f[0]) > 1 else ""


def netlist():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "net")
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", path,
                        os.path.join(HERE, PROJECT + ".kicad_sch")], check=True, stdout=subprocess.DEVNULL)
        tree = parse(tokens(open(path).read()))[0][0]
    comps = {}
    for c in find(find(tree, "components")[0], "comp"):
        props = {one(p, "name"): one(p, "value") for p in find(c, "property")}
        comps[one(c, "ref")] = {"value": one(c, "value"), "fp": one(c, "footprint"), "lcsc": props.get("LCSC", ""),
                                "path": one(c, "tstamps")}
    nets = {}
    for n in find(find(tree, "nets")[0], "net"):
        for node in find(n, "node"):
            nets[(one(node, "ref"), one(node, "pin"))] = one(n, "name")
    return comps, nets


def load(fp):
    lib, name = fp.split(":")
    folder = os.path.join(HERE, lib + ".pretty") if lib == PROJECT else os.path.join(FPDIR, lib + ".pretty")
    f = pcbnew.FootprintLoad(folder, name)
    if f is None:
        raise SystemExit("no footprint %s" % fp)
    f.SetFPID(pcbnew.LIB_ID(lib, name))
    return f


def put(board, f, x, y, rot, anchor="pads"):
    f.SetOrientationDegrees(rot)
    f.SetPosition(pt(x, y))
    if anchor == "pads":
        box = pcbnew.BOX2I()
        for p in f.Pads():
            box.Merge(p.GetPosition())
        f.Move(pt(x, y) - box.GetCenter())
    board.Add(f)


def rect(board, x0, y0, x1, y1, layer, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(pt(x0, y0))
    s.SetEnd(pt(x1, y1))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    board.Add(s)


def label(board, s, x, y, layer=pcbnew.Dwgs_User, size=1.0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * 0.15))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    board.Add(t)


def main():
    comps, nets = netlist()
    missing = sorted(set(comps) - set(PLACE))
    if missing or set(PLACE) - set(comps):
        raise SystemExit("not placed: %s; not in the schematic: %s" % (missing, sorted(set(PLACE) - set(comps))))
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(4)
    rect(board, 0, 0, PCB_X, PCB_Y, pcbnew.Edge_Cuts)
    netinfo = {}
    for name in sorted(set(nets.values())):
        netinfo[name] = pcbnew.NETINFO_ITEM(board, name)
        board.Add(netinfo[name])
    for ref in sorted(comps, key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r)))):
        c = comps[ref]
        f = load(c["fp"])
        f.SetReference(ref)
        f.SetValue(c["value"])
        f.SetPath(pcbnew.KIID_PATH("/" + c["path"]))
        if c["lcsc"]:
            f.SetField("LCSC", c["lcsc"])
            f.GetField("LCSC").SetVisible(False)
        for p in f.Pads():
            net = nets.get((ref, p.GetNumber()))
            if net:
                p.SetNet(netinfo[net])
        put(board, f, *PLACE[ref])
    for i, (x, y) in enumerate(HOLES):
        f = load("MountingHole:MountingHole_2.7mm_M2.5")
        f.SetReference("H%d" % (i + 1))
        f.SetAttributes(f.GetAttributes() | pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        put(board, f, x, y, 0, "origin")
    for name, x0, y0, x1, y1 in OVERHEAD:
        rect(board, x0, y0, x1, y1, pcbnew.Dwgs_User)
        label(board, name, x0 + 0.6, y1 - 1.2)
    rect(board, -2.6, SENSOR_GRILLE[0], -0.6, SENSOR_GRILLE[1], pcbnew.Dwgs_User)
    label(board, "GRILLE", -2.4, SENSOR_GRILLE[1] + 1.5)
    for side, x, y in [("A back", 44, -4), ("C front", 44, 75), ("D", -6, 36), ("B", 102, 36)]:
        label(board, side, x, y, size=1.5)
    pcbnew.SaveBoard(os.path.join(HERE, PROJECT + ".kicad_pcb"), board)
    table = '(fp_lib_table\n\t(version 7)\n\t(lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.pretty")(options "")(descr ""))\n)\n'
    open(os.path.join(HERE, "fp-lib-table"), "w").write(table % (PROJECT, PROJECT))


main()
