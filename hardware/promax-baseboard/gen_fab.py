#!/usr/bin/env python3
"""Writes what JLCPCB needs into fab/: the Gerber and drill files as one zip, the parts list and the placement list.

Run gen_pcb.py first. Needs KiCad's pcbnew module and kicad-cli. The lists follow JLCPCB's column names.
Look at the placement preview on JLCPCB's order page before paying: angles are corrected per part number
in the JLC table below, and a part that is new to the board is not in it.
"""
import csv
import math
import os
import re
import shutil
import subprocess
import zipfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = "baseboard"
BOARD = os.path.join(HERE, PROJECT + ".kicad_pcb")
OUT = os.path.join(HERE, "fab")
LAYERS = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"


def run(*args):
    subprocess.run(["kicad-cli"] + list(args), check=True, stdout=subprocess.DEVNULL)


def parts(board):
    """Footprints that are bought and fitted: those with an LCSC number."""
    for f in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        if f.HasField("LCSC") and f.GetFieldText("LCSC"):
            yield f


# JLCPCB places a part by its own library footprint: that footprint's origin, and its drawing as zero degrees.
# Footprints in baseboard.pretty came from that library and agree with it. For parts on a KiCad footprint this
# gives, by LCSC number, how far JLCPCB's footprint must turn (counter-clockwise) to lie on KiCad's, and where
# its origin then is in KiCad's footprint (x right, y down). Found by fetching each part's footprint with
# easyeda2kicad and matching pads of the same number; two-pad chip parts need nothing.
JLC = {
    "C311983": (270, 0, 0),      # TPS54302, SOT-23-6
    "C51118": (270, 0, 0),       # AP2112K, SOT-23-5
    "C38987": (180, 0, 0),       # 24AA02E48, SOT-23-5: this part's footprint is drawn the other way
    "C9866": (270, 0, 0),        # DS3231SN, SOIC-16W
    "C2937625": (270, 0, 2.54),  # 1x3 pin header: KiCad's origin is pin 1
    "C2691448": (270, 0, 3.81),  # 1x4 pin header
    "C181864": (0, 1.27, 0), "C417350": (0, 1.27, 0), "C99771": (0, 1.27, 0),   # LEDs: KiCad's origin is pin 1
    "C114218": (0, -0.08, -0.17),   # card socket
}


def placement(f):
    """Where JLCPCB's footprint for this part sits (board units) and at what angle."""
    turn, tx, ty = JLC.get(f.GetFieldText("LCSC"), (0, 0, 0))
    rho = math.radians(f.GetOrientationDegrees())
    dx = tx * math.cos(rho) + ty * math.sin(rho)
    dy = -tx * math.sin(rho) + ty * math.cos(rho)
    p = f.GetPosition()
    return p.x + pcbnew.FromMM(dx), p.y + pcbnew.FromMM(dy), (f.GetOrientationDegrees() + turn) % 360


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    gerbers = os.path.join(OUT, "gerbers")
    os.makedirs(gerbers)
    run("pcb", "export", "gerbers", "-o", gerbers + "/", "--layers", LAYERS, "--no-x2", "--no-netlist",
        "--subtract-soldermask", BOARD)
    # No drill map: JLCPCB's viewer lays it over the board, legend and all, as if it were a layer.
    run("pcb", "export", "drill", "-o", gerbers + "/", "--excellon-separate-th", "--excellon-oval-format", "alternate", BOARD)
    with zipfile.ZipFile(os.path.join(OUT, PROJECT + "-gerbers.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(gerbers)):
            z.write(os.path.join(gerbers, name), name)
    board = pcbnew.LoadBoard(BOARD)
    groups = {}
    for f in parts(board):
        # "0805", not "C_0805_2012Metric_...": JLCPCB compares this text with the part's package name.
        package = re.sub(r"^[RC]_(\d{4})_.*", r"\1", f.GetFPID().GetLibItemName().wx_str())
        key = (f.GetValue(), package, f.GetFieldText("LCSC"))
        groups.setdefault(key, []).append(f.GetReference())
    with open(os.path.join(OUT, PROJECT + "-bom.csv"), "w", newline="") as out:
        w = csv.writer(out)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, fp, lcsc), refs in sorted(groups.items(), key=lambda g: g[1][0]):
            w.writerow([value, ",".join(refs), fp, lcsc])
    with open(os.path.join(OUT, PROJECT + "-cpl.csv"), "w", newline="") as out:
        w = csv.writer(out)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for f in parts(board):
            x, y, angle = placement(f)
            # Same frame as the Gerber files: the sheet's, with y upwards.
            w.writerow([f.GetReference(), "%.4fmm" % pcbnew.ToMM(x), "%.4fmm" % -pcbnew.ToMM(y),
                        "bottom" if f.IsFlipped() else "top", "%g" % angle])
    print("%d kinds of part, %d parts" % (len(groups), sum(len(r) for r in groups.values())))


main()
