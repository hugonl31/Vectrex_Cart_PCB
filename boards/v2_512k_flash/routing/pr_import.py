"""pr_import.py BOARD ROUTES.json OUT - the neat router's stubs, tracks and vias into a (placed, track-free) KiCad
board; collinear pieces joined; GND zones refilled; saved. Run with KiCad's Python."""
import sys, json, math
try:
    import wx; wx.DisableAsserts()
except Exception:
    pass
import pcbnew
IN, RT, OUT = sys.argv[1:4]
b = pcbnew.LoadBoard(IN)
rt = json.load(open(RT))
mm = pcbnew.FromMM
V = lambda x, y: pcbnew.VECTOR2I(mm(x), mm(y))
nets = {}
for t in rt['stubs'] + rt['tracks']:
    nets.setdefault(t['net'], None)
for v in rt['vias']:
    nets.setdefault(v['net'], None)
for n in list(nets):
    nets[n] = b.FindNet(n)
nt = nv = 0
for t in rt['stubs'] + rt['tracks']:
    lay = pcbnew.F_Cu if t['layer'] == 'F' else pcbnew.B_Cu
    pts = t['pts']
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
            continue
        tr = pcbnew.PCB_TRACK(b); tr.SetStart(V(x1, y1)); tr.SetEnd(V(x2, y2))
        tr.SetWidth(mm(t['w'])); tr.SetLayer(lay); tr.SetNet(nets[t['net']]); b.Add(tr); nt += 1
for v in rt['vias']:
    via = pcbnew.PCB_VIA(b); via.SetPosition(V(v['x'], v['y']))
    via.SetFrontWidth(mm(0.762)); via.SetDrill(mm(0.508)); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(nets[v['net']]); b.Add(via); nv += 1
# loose ends: a route that ended on its own net's copper a hair beside it on the grid (KiCad wants the end
# inside the other copper): a short piece to the nearest point of that copper (same net, same layer)
def closest_on_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay; L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
    return ax + t * dx, ay + t * dy
uid = lambda o: o.m_Uuid.AsString()
def touching(x, y, lay, net, self_t):
    P = V(x, y); su = uid(self_t)
    for t in b.Tracks():
        if uid(t) == su or t.GetNetname() != net:
            continue
        if t.GetClass() == 'PCB_VIA':
            if t.HitTest(P): return True
        elif t.GetLayer() == lay and t.HitTest(P):
            return True
    for fp in b.Footprints():
        for pd in fp.Pads():
            if pd.GetNetname() == net and pd.IsOnLayer(lay) and pd.HitTest(P):
                return True
    return False
fixed = 0
tracks_now = [t for t in b.Tracks() if t.GetClass() == 'PCB_TRACK']
for t in tracks_now:
    net, lay = t.GetNetname(), t.GetLayer()
    for P in (t.GetStart(), t.GetEnd()):
        x, y = pcbnew.ToMM(P.x), pcbnew.ToMM(P.y)
        if touching(x, y, lay, net, t):
            continue
        best = None
        for o in b.Tracks():
            if uid(o) == uid(t) or o.GetNetname() != net:
                continue
            if o.GetClass() == 'PCB_VIA':
                q = (pcbnew.ToMM(o.GetPosition().x), pcbnew.ToMM(o.GetPosition().y))
            elif o.GetLayer() == lay:
                q = closest_on_seg(x, y, pcbnew.ToMM(o.GetStart().x), pcbnew.ToMM(o.GetStart().y), pcbnew.ToMM(o.GetEnd().x), pcbnew.ToMM(o.GetEnd().y))
            else:
                continue
            dd = math.hypot(q[0] - x, q[1] - y)
            if dd < 0.45 and (best is None or dd < best[0]): best = (dd, q)
        for fp in b.Footprints():
            for pd in fp.Pads():
                if pd.GetNetname() == net and pd.IsOnLayer(lay):
                    q = (pcbnew.ToMM(pd.GetPosition().x), pcbnew.ToMM(pd.GetPosition().y))
                    dd = math.hypot(q[0] - x, q[1] - y) - pcbnew.ToMM(min(pd.GetSize().x, pd.GetSize().y)) / 2
                    if dd < 0.45 and (best is None or dd < best[0]): best = (dd, q)
        if best and best[0] > 1e-4:
            tr = pcbnew.PCB_TRACK(b); tr.SetStart(P); tr.SetEnd(V(*best[1])); tr.SetWidth(t.GetWidth()); tr.SetLayer(lay)
            tr.SetNet(t.GetNet()); b.Add(tr); fixed += 1
print('loose ends joined:', fixed)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard(OUT, b)
print('tracks %d vias %d failed jobs %d -> %s' % (nt, nv, len(rt['failed']), OUT))
