#!/usr/bin/env python3
"""Pictures of the model: render.py OUT VIEWS STEPDIR [hide,names] [ghost,names]

VIEWS is a comma list of front, back, top, left, side, face. Hidden parts are left out and
ghost parts are drawn see-through. Needs CadQuery and vtk; works without a display.
"""
import sys

import cadquery as cq
import vtk

out, views, src = sys.argv[1], sys.argv[2].split(","), sys.argv[3]
hide = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else set()
ghost = set(sys.argv[5].split(",")) if len(sys.argv) > 5 else set()
colours = {"base_bottom": (.3, .3, .3), "base_shell": (.85, .85, .82), "yoke": (.55, .6, .7), "head": (.85, .85, .82),
           "baseboard": (.1, .45, .2), "promax": (.15, .15, .15), "pan_servo": (.2, .3, .8),
           "camera": (.1, .5, .25), "oled": (.15, .3, .75)}
ren = vtk.vtkRenderer()
ren.SetBackground(1, 1, 1)
for name, c in colours.items():
    if name in hide:
        continue
    shape = cq.importers.importStep("%s/%s.step" % (src, name)).val()
    verts, tris = shape.tessellate(0.1, 0.3)
    pts = vtk.vtkPoints()
    for v in verts:
        pts.InsertNextPoint(v.x, v.y, v.z)
    cells = vtk.vtkCellArray()
    for t in tris:
        cells.InsertNextCell(3, t)
    pd = vtk.vtkPolyData()
    pd.SetPoints(pts)
    pd.SetPolys(cells)
    nrm = vtk.vtkPolyDataNormals()
    nrm.SetInputData(pd)
    nrm.SetFeatureAngle(30)
    m = vtk.vtkPolyDataMapper()
    m.SetInputConnection(nrm.GetOutputPort())
    a = vtk.vtkActor()
    a.SetMapper(m)
    a.GetProperty().SetColor(*c)
    if name in ghost:
        a.GetProperty().SetOpacity(0.25)
    ren.AddActor(a)
win = vtk.vtkRenderWindow()
win.SetOffScreenRendering(1)
win.AddRenderer(ren)
win.SetSize(900, 800)
dirs = {"front": (0.6, 1.4, 0.8), "back": (-0.6, -1.4, 0.8), "top": (0.001, -0.02, 1), "left": (-1.4, 0.5, 0.6),
        "side": (1, 0.02, 0.05), "face": (0.02, 1, 0.05)}
for v in views:
    cam = ren.GetActiveCamera()
    d = dirs[v]
    cam.SetFocalPoint(0, 0, 0)
    cam.SetPosition(d[0] * 300, d[1] * 300, d[2] * 300)
    cam.SetViewUp(0, 1 if v == "top" else 0, 0 if v == "top" else 1)
    ren.ResetCamera()
    win.Render()
    f = vtk.vtkWindowToImageFilter()
    f.SetInput(win)
    f.Update()
    w = vtk.vtkPNGWriter()
    w.SetFileName("%s-%s.png" % (out, v))
    w.SetInputConnection(f.GetOutputPort())
    w.Write()
