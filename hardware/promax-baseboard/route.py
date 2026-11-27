"""Tracks, vias and planes of the baseboard. gen_pcb.py calls route(); there is nothing to run here.

Layers: F.Cu parts and signals, In1.Cu ground, In2.Cu 3.3 V with the other rails as wide tracks, B.Cu signals.
The power path is drawn by hand in power(); the rest is found by a search on a grid, short nets first.
Positions are in the board's axes, as in gen_pcb.py.
"""
import heapq
import math

import numpy as np
import pcbnew

G = 0.127            # grid; the Pro Max pins fall on it
CLEAR = 0.2
HW = 0.125           # half the default track width
VIA_R, VIA_DRILL = 0.3, 0.3
EDGE = 0.5
GROW = HW + CLEAR    # how far copper keeps a default track's centre away
PLANES = {"GND": 1, "3V3_B": 2}          # net: inner layer
GROUNDED_SHELL = ("J10",)                # only solder mask would separate a via from the card socket's shell
LAYERS = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
F, IN2, B = 0, 2, 3
# Nets the search routes wider than the default, or on other layers than F and B.
SPEC = {"VSYS": (1.0, (F,)), "V_SERVO": (1.2, (IN2,)), "/3V3_CORE": (0.4, (F, B)), "VIN": (0.3, (F, B))}
BEND, SQUARE, VIA_COST = 2.0, 6.0, 80.0   # in grid steps; a via counts as 10 mm of track
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


def dilate(b, k):
    out = b.copy()
    for s in range(1, k + 1):
        out[s:, :] |= b[:-s, :]
        out[:-s, :] |= b[s:, :]
    b = out.copy()
    for s in range(1, k + 1):
        out[:, s:] |= b[:, :-s]
        out[:, :-s] |= b[:, s:]
    return out


class Router:
    def __init__(self, board, size, to_board, from_board):
        self.board, self.to_board = board, to_board
        self.w, self.h = size
        self.x0 = 78.62 % G
        self.y0 = 22.38 % G
        self.nx, self.ny = int(self.w / G) + 1, int(self.h / G) + 1
        self.n = self.nx * self.ny
        self.xs = self.x0 + np.arange(self.nx)[:, None] * G
        self.ys = self.y0 + np.arange(self.ny)[None, :] * G
        self.owner = [np.zeros((self.nx, self.ny), np.int32) for _ in LAYERS]
        self.smd = np.zeros((self.nx, self.ny), bool)       # no via in a surface pad
        self.under = np.zeros((self.nx, self.ny), bool)     # under a grounded metal shell: ground vias only
        self.ids, self.names = {}, {}
        self.tree = {}                                       # net: cells known to be joined, per layer
        self.pads = []
        self.failed = []
        self.by_hand = set()                                 # pads whose hand-drawn track is marked only at its tip
        margin = EDGE + HW
        for o in self.owner:
            o[(self.xs < margin) | (self.xs > self.w - margin) | (self.ys < margin) | (self.ys > self.h - margin)] = -1
        for f in board.GetFootprints():
            if f.GetReference() in GROUNDED_SHELL:
                bb = f.GetCourtyard(pcbnew.F_Cu).BBox()
                xa, ya = from_board(bb.GetLeft(), bb.GetBottom())
                xb, yb = from_board(bb.GetRight(), bb.GetTop())
                self.under |= self.box(xa, ya, xb, yb, VIA_R)
            for z in f.Zones():                             # the footprint's own keep-out areas
                bb = z.GetBoundingBox()
                xa, ya = from_board(bb.GetLeft(), bb.GetBottom())
                xb, yb = from_board(bb.GetRight(), bb.GetTop())
                self.own(F, self.box(xa, ya, xb, yb, HW + 0.02), -1)
                self.smd |= self.box(xa, ya, xb, yb, VIA_R + 0.02)
            for p in f.Pads():
                bb = p.GetBoundingBox()
                xa, ya = from_board(bb.GetLeft(), bb.GetBottom())
                xb, yb = from_board(bb.GetRight(), bb.GetTop())
                cx, cy = from_board(p.GetPosition().x, p.GetPosition().y)
                hole = p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
                through = hole or p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
                net = -1 if hole or not p.GetNetname() else self.net(p.GetNetname())
                if f.GetReference().startswith("H"):
                    self.disc(range(4), cx, cy, 3.0, -1)     # where the enclosure's column lands
                for l in range(4) if through else [F]:
                    self.rect(l, xa, ya, xb, yb, net, GROW + (0.05 if hole else 0))
                if not through:
                    self.smd |= self.box(xa, ya, xb, yb, VIA_R + 0.05)
                if net > 0:
                    self.pads.append({"ref": f.GetReference(), "num": p.GetNumber(), "net": p.GetNetname(), "x": cx, "y": cy,
                                      "box": (xa, ya, xb, yb), "layers": list(range(4)) if through else [F]})
                    if through and p.GetNetname() in PLANES:
                        self.mark(p.GetNetname(), range(4), cx, cy, cx, cy)

    # ---- the grid ----
    def net(self, name):
        if name not in self.ids:
            self.ids[name] = len(self.ids) + 1
            self.names[self.ids[name]] = name
            self.tree[name] = [np.zeros((self.nx, self.ny), bool) for _ in LAYERS]
        return self.ids[name]

    def cell(self, x, y):
        return int(round((x - self.x0) / G)), int(round((y - self.y0) / G))

    def at(self, i, j):
        return self.x0 + i * G, self.y0 + j * G

    def box(self, xa, ya, xb, yb, grow):
        return (self.xs >= xa - grow) & (self.xs <= xb + grow) & (self.ys >= ya - grow) & (self.ys <= yb + grow)

    def near(self, ax, ay, bx, by, r):
        """Cells within r of the segment a-b."""
        dx, dy = bx - ax, by - ay
        d2 = dx * dx + dy * dy
        t = 0 if d2 == 0 else np.clip(((self.xs - ax) * dx + (self.ys - ay) * dy) / d2, 0, 1)
        return (self.xs - ax - t * dx) ** 2 + (self.ys - ay - t * dy) ** 2 <= r * r

    def own(self, l, mask, net):
        o = self.owner[l]
        if net < 0:
            o[mask] = -1
            return
        o[mask & (o == 0)] = net
        o[mask & (o != net)] = -1

    def rect(self, l, xa, ya, xb, yb, net, grow):
        self.own(l, self.box(xa, ya, xb, yb, grow), net)

    def disc(self, layers, x, y, r, net):
        for l in layers:
            self.own(l, self.near(x, y, x, y, r), net)

    def mark(self, name, layers, ax, ay, bx, by):
        self.net(name)
        for l in layers:
            self.tree[name][l] |= self.near(ax, ay, bx, by, G * 0.75)

    # ---- copper ----
    def track(self, name, l, width, pts, tip=False):
        """With tip, later tracks may join only at the last point."""
        net = self.board.FindNet(name)
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(self.to_board(ax, ay))
            t.SetEnd(self.to_board(bx, by))
            t.SetWidth(pcbnew.FromMM(width))
            t.SetLayer(LAYERS[l])
            t.SetNet(net)
            self.board.Add(t)
            self.own(l, self.near(ax, ay, bx, by, width / 2 + GROW), self.net(name))
            if not tip:
                self.mark(name, [l], ax, ay, bx, by)
        if tip:
            self.mark(name, [l], *pts[-1], *pts[-1])

    def via(self, name, x, y):
        v = pcbnew.PCB_VIA(self.board)
        v.SetPosition(self.to_board(x, y))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(2 * VIA_R))
        v.SetDrill(pcbnew.FromMM(VIA_DRILL))
        v.SetNet(self.board.FindNet(name))
        self.board.Add(v)
        self.disc(range(4), x, y, VIA_R + GROW, self.net(name))
        self.mark(name, range(4), x, y, x, y)

    def pad(self, ref, num):
        return next(p for p in self.pads if p["ref"] == ref and p["num"] == str(num))

    # ---- the search ----
    def blocked(self, name, width):
        """Per layer, where a track of this net may not have its centre; and where a via may sit."""
        net = self.net(name)
        base = [(o != 0) & (o != net) for o in self.owner]
        k = max(0, math.ceil((width / 2 - HW) / G - 1e-6))
        blk = [dilate(b, k) if k else b for b in base]
        kv = math.ceil((VIA_R - HW) / G - 1e-6)
        via = ~self.smd if name == "GND" else ~(self.smd | self.under)
        for b in base:
            via &= ~dilate(b, kv)
        return blk, via

    def search(self, layers, blk, viaok, sources, goal, box):
        """A* over (layer, cell, heading). goal is a mask per layer; box bounds it for the estimate."""
        ny, n = self.ny, self.n
        bl = {l: blk[l].tobytes() for l in layers}
        gl = {l: goal[l].tobytes() for l in layers}
        vk = viaok.tobytes() if viaok is not None else None
        i0, i1, j0, j1 = box if box else (0, 0, 0, 0)

        def est(i, j):
            if not box:
                return 0.0
            dx = i0 - i if i < i0 else i - i1 if i > i1 else 0
            dy = j0 - j if j < j0 else j - j1 if j > j1 else 0
            return dx + dy - 0.5858 * min(dx, dy)

        best, parent, heap = {}, {}, []
        for l, i, j in sources:
            key = (l * n + i * ny + j) * 9 + 8
            best[key] = 0.0
            heapq.heappush(heap, (est(i, j), 0.0, key))
        while heap:
            _, g, key = heapq.heappop(heap)
            if best[key] < g:
                continue
            s, d = divmod(key, 9)
            l, idx = divmod(s, n)
            if gl[l][idx]:
                path = []
                while True:
                    s = key // 9
                    path.append((s // n,) + divmod(s % n, ny))
                    if key not in parent:
                        return path[::-1]
                    key = parent[key]
            i, j = divmod(idx, ny)
            b = bl[l]
            for nd in range(8):
                cost = 1.4142 if nd & 1 else 1.0
                if d < 8:
                    turn = abs(nd - d)
                    turn = 8 - turn if turn > 4 else turn
                    if turn > 2:
                        continue
                    cost += (0.0, BEND, SQUARE)[turn]
                di, dj = DIRS[nd]
                nidx = idx + di * ny + dj
                if b[nidx] or (nd & 1 and (b[idx + di * ny] or b[idx + dj])):
                    continue
                nkey = (l * n + nidx) * 9 + nd
                ng = g + cost
                if ng < best.get(nkey, 1e18):
                    best[nkey] = ng
                    parent[nkey] = key
                    heapq.heappush(heap, (ng + est(i + di, j + dj), ng, nkey))
            if vk and vk[idx]:
                for l2 in layers:
                    if l2 != l and not bl[l2][idx]:
                        nkey = (l2 * n + idx) * 9 + 8
                        ng = g + VIA_COST
                        if ng < best.get(nkey, 1e18):
                            best[nkey] = ng
                            parent[nkey] = key
                            heapq.heappush(heap, (ng + est(i, j), ng, nkey))
        return None

    def lay(self, name, width, path):
        """Path of cells to tracks and vias."""
        run = [path[0]]
        for prev, cur in zip(path, path[1:]):
            if cur[0] != prev[0]:
                self.flush(name, width, run)
                self.via(name, *self.at(prev[1], prev[2]))
                run = [cur]
            else:
                run.append(cur)
        self.flush(name, width, run)

    def flush(self, name, width, run):
        if len(run) < 2:
            return
        pts = [run[0]]
        for a, b, c in zip(run, run[1:], run[2:]):
            if (b[1] - a[1], b[2] - a[2]) != (c[1] - b[1], c[2] - b[2]):
                pts.append(b)
        pts.append(run[-1])
        self.track(name, run[0][0], width, [self.at(p[1], p[2]) for p in pts])

    def bounds(self, goal, layers):
        ii, jj = np.nonzero(np.logical_or.reduce([goal[l] for l in layers]))
        return (ii.min(), ii.max(), jj.min(), jj.max()) if len(ii) else None

    def link(self, name, width, layers, a, b):
        """A run between two points that already carry this net's copper, without vias."""
        blk, _ = self.blocked(name, width)
        goal = [np.zeros((self.nx, self.ny), bool) for _ in LAYERS]
        ci, cj = self.cell(*b)
        for l in layers:
            goal[l][ci, cj] = True
        path = self.search(layers, blk, None, [(l,) + self.cell(*a) for l in layers], goal, (ci, ci, cj, cj))
        if not path:
            self.failed.append("%s link %s-%s" % (name, a, b))
            return
        self.lay(name, width, path)

    def joined(self, p):
        if (p["ref"], p["num"]) in self.by_hand:
            return True
        i0, j0 = self.cell(p["box"][0], p["box"][1])
        i1, j1 = self.cell(p["box"][2], p["box"][3])
        return any(self.tree[p["net"]][l][i0:i1 + 1, j0:j1 + 1].any() for l in p["layers"])

    def fanout(self, name):
        """Every surface pad of a plane net gets a via, or a track to a hole that is already on the plane."""
        todo = [p for p in self.pads if p["net"] == name and p["layers"] == [F] and not self.joined(p)]
        for p in sorted(todo, key=lambda p: (p["x"], p["y"])):
            for width in (0.4, 0.25):
                blk, viaok = self.blocked(name, width)
                goal = [np.zeros((self.nx, self.ny), bool) for _ in LAYERS]
                goal[F] = (viaok & ~blk[F]) | self.tree[name][F]
                path = self.search([F], blk, None, [(F,) + self.cell(p["x"], p["y"])], goal, None)
                if path:
                    break
            if not path:
                self.failed.append("%s %s.%s to its plane" % (name, p["ref"], p["num"]))
                continue
            on_plane = self.tree[name][F][path[-1][1], path[-1][2]]
            self.lay(name, width, path)
            if not on_plane:
                self.via(name, *self.at(path[-1][1], path[-1][2]))

    def connect(self, name):
        """Joins the net's pads one at a time to what is already joined."""
        width, layers = SPEC.get(name, (2 * HW, (F, B)))
        pads = [p for p in self.pads if p["net"] == name and set(p["layers"]) & set(layers)]
        tree = self.tree[name]
        if not any(t.any() for t in tree):
            p = pads[0]
            self.mark(name, p["layers"], p["x"], p["y"], p["x"], p["y"])
        while True:
            todo = [p for p in pads if not self.joined(p)]
            if not todo:
                return
            for l in range(4):
                if l not in layers:
                    tree[l][:] = False        # copper there cannot be reached
            box = self.bounds(tree, layers)
            ci, cj = (box[0] + box[1]) / 2, (box[2] + box[3]) / 2
            p = min(todo, key=lambda p: abs(self.cell(p["x"], p["y"])[0] - ci) + abs(self.cell(p["x"], p["y"])[1] - cj))
            for w in sorted({width, min(width, 0.5), 2 * HW}, reverse=True):
                blk, viaok = self.blocked(name, w)
                src = [(l,) + self.cell(p["x"], p["y"]) for l in p["layers"] if l in layers]
                path = self.search(layers, blk, viaok if len(layers) > 1 else None, src, tree, box)
                if path:
                    break
            if not path:
                self.failed.append("%s %s.%s" % (name, p["ref"], p["num"]))
                pads.remove(p)
                continue
            if w != width:
                print("  %s %s.%s at %.2f mm instead of %.2f" % (name, p["ref"], p["num"], w, width))
            self.lay(name, w, path)
            self.mark(name, p["layers"], p["x"], p["y"], p["x"], p["y"])

    def span(self, name):
        pads = [p for p in self.pads if p["net"] == name]
        return max(p["x"] for p in pads) - min(p["x"] for p in pads) + max(p["y"] for p in pads) - min(p["y"] for p in pads)


def buck(r, x, y, out, feed):
    """The copper around one TPS54302; offsets from the chip, pins 1-3 on the left with pin 1 at the top."""
    n = "1" if out == "5V_BASE" else "2"
    sw, bst, fb = "/SW" + n, "/BST" + n, "/FB" + n

    def t(name, width, pts, l=F):
        r.track(name, l, width, [(x + dx, y + dy) for dx, dy in pts])

    # Input: both capacitors and pin 3 on one line, ground the same above it.
    t("VIN", 1.0, [feed, (-6.5, -1.1), (-4.2, -1.1)])
    t("VIN", 0.6, [(-4.2, -1.1), (-1.14, -1.1)])
    t("GND", 1.0, [(-6.5, 1.1), (-4.2, 1.1)])
    t("GND", 0.6, [(-4.2, 1.1), (-1.14, 1.1)])
    t("GND", 0.6, [(-4.2, 1.1), (-4.2, 2.9)])
    t("GND", 0.6, [(-6.5, 1.1), (-6.5, 2.4)])
    r.via("GND", x - 4.2, y + 2.9)
    r.via("GND", x - 6.5, y + 2.4)
    # Switch node: out under the chip, down to the inductor, up and round to the bootstrap capacitor.
    t(sw, 0.4, [(-1.14, 0), (0, 0), (0, -2.0)])
    t(sw, 1.0, [(0, -2.0), (-3.9, -5.9)])
    t(sw, 0.3, [(0, 0), (0, 2.0), (1.1, 3.1), (5.23, 3.1), (5.23, 1.7)])
    t(bst, 0.3, [(1.14, 0.95), (1.9, 0.95), (2.65, 1.7), (3.17, 1.7)])
    t(fb, 0.3, [(1.14, -0.95), (2.0, -0.95), (2.35, -1.3), (9.7 if n == "2" else 7.6, -1.3)])
    # Output: inductor to both capacitors, the divider's top, and three vias down to In2.
    t(out, 1.5, [(1.42, -5.6), (4.64, -5.6)])
    t(out, 1.2, [(4.64, -5.6), (4.64, -8.1)])
    t(out, 0.4, [(4.64, -5.6), (5.5, -4.74), (5.5, -3.3), (7.6, -3.3)])
    t(out, 0.8, [(3.3, -5.2), (3.3, -7.4)])
    t(out, 0.8, [(3.3, -5.2), (3.3, -7.4)], IN2)
    for dy in (-5.2, -6.3, -7.4):
        r.via(out, x + 3.3, y + dy)
    for dy in (-5.6, -8.1):
        t("GND", 0.8, [(7.76, dy), (9.0, dy)])
        r.via("GND", x + 9.0, y + dy)


def power(r, bucks):
    # Jack and battery, each through its diode to the fuse.
    r.track("/VJACK", F, 1.5, [(19.0, 10.25), (19.0, 17.5), (19.5, 18.0)])
    r.track("/VIN_OR", F, 1.2, [(23.5, 18.0), (24.6, 18.0), (27.4, 15.2), (29.2, 15.2), (36.0, 15.2)])
    r.track("/VBAT", F, 1.2, [(35.5, 4.2), (35.5, 9.0), (40.0, 13.5), (40.0, 15.0)])
    # From the fuse past the bulk capacitor to both regulators.
    r.track("VIN", F, 1.2, [(26.6, 19.7), (29.2, 19.7), (35.8, 19.7), (42.8, 19.7), (43.7, 19.7)])
    r.track("VIN", F, 1.2, [(35.8, 19.7), (35.8, 22.5)])
    r.track("VIN", F, 0.8, [(43.7, 19.7), (43.7, 23.2)])
    r.track("VIN", F, 1.0, [(42.8, 19.7), (42.8, 9.7)])
    (x1, y1), (x2, y2) = bucks
    buck(r, x1, y1, "5V_BASE", (42.8 - x1, -1.1))
    buck(r, x2, y2, "V_SERVO", (43.7 - x2, -1.1))
    # The surge diode hangs on VIN by a track on the back, under the diode-OR.
    r.track("VIN", F, 1.2, [(29.1, 6.0), (27.2, 6.0)])
    r.track("VIN", F, 0.8, [(27.2, 5.4), (27.2, 6.6)])
    r.track("VIN", B, 1.0, [(27.2, 6.6), (26.6, 7.2), (26.6, 20.2)])
    for x, y in [(27.2, 5.4), (27.2, 6.6), (26.6, 19.2), (26.6, 20.2)]:
        r.via("VIN", x, y)
    r.track("GND", F, 1.2, [(29.1, 10.0), (31.0, 10.0)])
    r.track("GND", F, 0.8, [(31.0, 9.5), (31.0, 10.5)])
    for x in (39.9, 41.2):
        r.track("GND", F, 0.8, [(x, 22.5), (x, 24.2)])
        r.via("GND", x, 24.2)
    # Servo capacitor and the diode to VSYS: two vias each.
    r.track("V_SERVO", F, 1.2, [(49.5, 45.8), (49.5, 43.5)])
    r.track("V_SERVO", F, 0.8, [(49.0, 43.5), (50.0, 43.5)])
    r.track("GND", F, 1.2, [(49.5, 51.2), (49.5, 53.5)])
    r.track("GND", F, 0.8, [(49.0, 53.5), (50.0, 53.5)])
    r.track("5V_BASE", F, 1.2, [(84.0, 68.6), (81.9, 68.6)])
    r.track("5V_BASE", F, 0.8, [(81.9, 68.1), (81.9, 69.1)])
    for name, x, y in [("GND", 31.0, 9.5), ("GND", 31.0, 10.5), ("V_SERVO", 49.0, 43.5), ("V_SERVO", 50.0, 43.5),
                       ("GND", 49.0, 53.5), ("GND", 50.0, 53.5), ("5V_BASE", 81.9, 68.1), ("5V_BASE", 81.9, 69.1)]:
        r.via(name, x, y)
    r.track("VIN", B, 0.8, [(27.2, 5.4), (27.2, 6.6)])
    r.track("V_SERVO", IN2, 0.8, [(49.0, 43.5), (50.0, 43.5)])
    r.track("5V_BASE", IN2, 0.8, [(81.9, 68.1), (81.9, 69.1)])
    # The sensor's footprint allows no copper under it, so its pads are left from their outer ends.
    r.track("/I2C3_SDA", F, 0.2, [(1.32, 57.4), (1.0, 57.4)], tip=True)
    r.track("/I2C3_SCL", F, 0.2, [(1.32, 56.6), (1.0, 56.6)], tip=True)
    r.by_hand |= {("U6", "1"), ("U6", "2")}
    r.track("3V3_B", F, 0.2, [(3.08, 56.6), (4.2, 56.6), (4.8, 56.0), (5.6, 56.0), (5.6, 54.8)])
    r.track("GND", F, 0.2, [(3.08, 57.4), (4.2, 57.4), (4.8, 58.0), (5.6, 58.0), (5.6, 59.2)])
    r.via("3V3_B", 5.6, 54.8)
    r.via("GND", 5.6, 59.2)
    # Card socket pins straight to their pull-ups, before anything else walls them in.
    for name, pts in [("/SD_D2", [(55.72, 55.28), (55.72, 52.2)]),
                      ("/SD_D3", [(56.82, 55.28), (56.82, 53.3), (57.3, 52.82), (57.3, 52.2)]),
                      ("/SD_CMD", [(57.92, 55.28), (57.92, 53.6), (59.3, 52.22)]),
                      ("/SD_D0", [(62.32, 55.28), (62.32, 52.2)]),
                      ("/SD_D1", [(63.43, 55.28), (63.43, 52.2)])]:
        r.track(name, F, 2 * HW, pts)
    r.track("3V3_B", F, 0.3, [(59.03, 55.28), (59.03, 53.95)])   # the socket's supply pin, to a via in front of it
    r.via("3V3_B", 59.03, 53.95)
    # The rails cross the board on In2.
    r.link("5V_BASE", 1.2, [IN2], (x1 + 3.3, y1 - 6.3), (81.9, 68.1))
    r.link("V_SERVO", 1.2, [IN2], (x2 + 3.3, y2 - 6.3), (49.0, 43.5))


def plane(board, name, layer, size, to_board, clearance=0.25):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(board.FindNet(name))
    o = z.Outline()
    o.NewOutline()
    for x, y in [(0, 0), (size[0], 0), (size[0], size[1]), (0, size[1])]:
        o.Append(to_board(x, y))
    z.SetLocalClearance(pcbnew.FromMM(clearance))
    z.SetMinThickness(pcbnew.FromMM(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(pcbnew.FromMM(0.3))
    z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.5))
    z.SetZoneName(name)
    board.Add(z)


def route(board, size, to_board, from_board, bucks, first=()):
    """Returns the nets that found no way; the caller starts again with those in first."""
    r = Router(board, size, to_board, from_board)
    power(r, bucks)
    rest = sorted((n for n in r.ids if n not in PLANES and not n.startswith("unconnected")),
                  key=lambda n: (n not in first, r.span(n)))
    card = [n for n in rest if n.startswith("/SD_")]         # the card socket's pins leave before vias crowd them
    for name in card:
        r.connect(name)
    for name in PLANES:
        r.fanout(name)
    for name in rest:
        if name not in card:
            r.connect(name)
    for name, l in PLANES.items():
        plane(board, name, LAYERS[l], size, to_board)
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):                 # ground fills what the tracks leave free
        plane(board, "GND", layer, size, to_board, clearance=0.3)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    for f in r.failed:
        print("no way for " + f)
    return sorted({f.split()[0] for f in r.failed})
