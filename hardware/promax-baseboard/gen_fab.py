#!/usr/bin/env python3
"""Writes what JLCPCB needs into fab/: the Gerber and drill files as one zip, the parts list and the placement list.

Run gen_pcb.py first. Needs KiCad's pcbnew module and kicad-cli. The lists follow JLCPCB's column names.
Look at the placement preview on JLCPCB's order page before paying: the rotation its library expects
differs from KiCad's for some packages, and this script does not correct for that.
"""
import csv
import os
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


def middle(f):
    """Where the part's middle is: the footprint's anchor for surface parts, the middle of the pins otherwise."""
    if f.GetAttributes() & pcbnew.FP_SMD:
        return f.GetPosition()
    box = pcbnew.BOX2I()
    for p in f.Pads():
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
            box.Merge(p.GetPosition())
    return box.GetCenter() if box.GetWidth() or box.GetHeight() or len(f.Pads()) == 1 else f.GetPosition()


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    gerbers = os.path.join(OUT, "gerbers")
    os.makedirs(gerbers)
    run("pcb", "export", "gerbers", "-o", gerbers + "/", "--layers", LAYERS, "--no-x2", "--no-netlist",
        "--subtract-soldermask", BOARD)
    run("pcb", "export", "drill", "-o", gerbers + "/", "--excellon-separate-th", "--excellon-oval-format", "alternate",
        "--generate-map", "--map-format", "gerberx2", BOARD)
    with zipfile.ZipFile(os.path.join(OUT, PROJECT + "-gerbers.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(gerbers)):
            z.write(os.path.join(gerbers, name), name)
    board = pcbnew.LoadBoard(BOARD)
    groups = {}
    for f in parts(board):
        key = (f.GetValue(), f.GetFPID().GetLibItemName().wx_str(), f.GetFieldText("LCSC"))
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
            m = middle(f)
            # Same frame as the Gerber files: the sheet's, with y upwards.
            w.writerow([f.GetReference(), "%.4fmm" % pcbnew.ToMM(m.x), "%.4fmm" % -pcbnew.ToMM(m.y),
                        "bottom" if f.IsFlipped() else "top", "%g" % (f.GetOrientationDegrees() % 360)])
    print("%d kinds of part, %d parts" % (len(groups), sum(len(r) for r in groups.values())))


main()
