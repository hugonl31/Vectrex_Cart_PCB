"""stitch.py IN OUT - GND stitching vias by connectivity: the GND fill is laid with islands kept, every piece of
it (front, back) is a node; GND pads and the socket's through-hole GND pins tie pieces together; a possible via
(a spot deep inside a front piece and a back piece) is an edge. From the large front fill, the fewest vias that
reach every piece with a GND pad are added (shortest paths), then a few more between the two large areas for a
solid ground. Islands left without a connection are removed again by the zones' own setting. KiCad Python."""
import sys, math, heapq
try:
    import wx; wx.DisableAsserts()
except Exception:
    pass
import pcbnew
IN, OUT = sys.argv[1:3]
b = pcbnew.LoadBoard(IN)
mm, MM = pcbnew.ToMM, pcbnew.FromMM
gnd = b.FindNet('GND')
VIA_D, VIA_DR = 0.762, 0.508
NEED = VIA_D / 2 + 0.06
F, B_ = pcbnew.F_Cu, pcbnew.B_Cu
filler = pcbnew.ZONE_FILLER(b)
MODES = []
for z in b.Zones():
    if z.GetNetname() == 'GND' and not z.GetIsRuleArea():
        MODES.append((z, z.GetIslandRemovalMode())); z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
filler.Fill(b.Zones())

nodes = []                                           # (layer, poly)
for z in b.Zones():
    if z.GetNetname() != 'GND' or z.GetIsRuleArea():
        continue
    for l in (F, B_):
        if not z.IsOnLayer(l):
            continue
        ps = z.GetFilledPolysList(l)
        for i in range(ps.OutlineCount()):
            one = pcbnew.SHAPE_POLY_SET(); one.AddOutline(ps.Outline(i))
            for h in range(ps.HoleCount(i)):
                one.AddHole(ps.Hole(i, h))
            nodes.append((l, one))
N = len(nodes)
area = [p.Area() / 1e12 for l, p in nodes]

def deep(poly, p):
    if not poly.Contains(p):
        return False
    for i in range(poly.OutlineCount()):
        for c in [poly.Outline(i)] + [poly.Hole(i, h) for h in range(poly.HoleCount(i))]:
            if mm(int(math.sqrt(c.SquaredDistance(p, True)))) < NEED:
                return False
    return True

def touches(poly, p, r):
    return poly.Collide(p, MM(r))

parent = list(range(N))
def find(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]; a = parent[a]
    return a
def union(a, c):
    parent[find(a)] = find(c)
want = set()                                         # pieces holding a GND pad: must reach the ground
for fp in b.Footprints():
    for pd in fp.Pads():
        if pd.GetNetname() != 'GND':
            continue
        pos = pd.GetPosition(); r = mm(max(pd.GetSize().x, pd.GetSize().y)) / 2 + 0.6
        hit = [k for k, (l, p) in enumerate(nodes) if pd.IsOnLayer(l) and touches(p, pos, r)]
        want.update(hit)
        for k in hit[1:]:
            union(hit[0], k)
for v in b.Tracks():
    if v.GetClass() == 'PCB_VIA' and v.GetNetname() == 'GND':
        hit = [k for k, (l, p) in enumerate(nodes) if touches(p, v.GetPosition(), VIA_D / 2 + 0.1)]
        for k in hit[1:]:
            union(hit[0], k)

def spot(pa, pb):
    """a via spot deep inside both pieces, nearest the middle of their overlap"""
    ba, bb_ = pa.BBox(), pb.BBox()
    x0, x1 = max(ba.GetLeft(), bb_.GetLeft()), min(ba.GetRight(), bb_.GetRight())
    y0, y1 = max(ba.GetTop(), bb_.GetTop()), min(ba.GetBottom(), bb_.GetBottom())
    if x0 >= x1 or y0 >= y1:
        return None
    cx, cy = (mm(x0) + mm(x1)) / 2, (mm(y0) + mm(y1)) / 2
    pts = []
    x = mm(x0)
    while x <= mm(x1):
        y = mm(y0)
        while y <= mm(y1):
            pts.append((x, y)); y += 0.25
        x += 0.25
    pts.sort(key=lambda q: (q[0] - cx) ** 2 + (q[1] - cy) ** 2)
    for x, y in pts:
        p = pcbnew.VECTOR2I(MM(x), MM(y))
        if deep(pa, p) and deep(pb, p):
            return (round(x, 3), round(y, 3))
    return None
edges = {}
for i in range(N):
    for j in range(N):
        if nodes[i][0] == F and nodes[j][0] == B_:
            s = spot(nodes[i][1], nodes[j][1])
            if s:
                edges.setdefault(i, []).append((j, s)); edges.setdefault(j, []).append((i, s))
main = max(range(N), key=lambda k: area[k] if nodes[k][0] == F else -1)

def add_via(x, y):
    v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    v.SetFrontWidth(MM(VIA_D)); v.SetDrill(MM(VIA_DR)); v.SetLayerPair(F, B_); v.SetNet(gnd); b.Add(v)
added = []

def connect(target):
    """the fewest vias from the main component to target (Dijkstra; within a component free)"""
    dist, prev, pq = {}, {}, []
    for k in range(N):
        if find(k) == find(main):
            dist[k] = 0; heapq.heappush(pq, (0, k))
    goal = find(target)
    while pq:
        d, k = heapq.heappop(pq)
        if d > dist.get(k, 1e9):
            continue
        if find(k) == goal:
            path = []
            while k in prev:
                k2, s = prev[k]; path.append((k2, k, s)); k = k2
            return path
        nbr = [(j, s, 1) for j, s in edges.get(k, [])] + [(j, None, 0) for j in range(N) if j != k and find(j) == find(k)]
        for j, s, c in nbr:
            if d + c < dist.get(j, 1e9):
                dist[j] = d + c; prev[j] = (k, s); heapq.heappush(pq, (d + c, j))
    return None
lost = 0
for t in sorted(want, key=lambda k: -area[k]):
    if find(t) == find(main):
        continue
    path = connect(t)
    if path is None:
        lost += 1
        print('no way to ground for a piece on %s, area %.1f mm2' % ('F' if nodes[t][0] == F else 'B', area[t])); continue
    for a, c, s in path:
        if s and s not in added:
            add_via(*s); added.append(s)
        union(a, c)
# a few more between the large front fill and large back pieces, spread out (a solid ground)
for k in [k for k in range(N) if nodes[k][0] == B_ and area[k] > 20]:
    for j, s in edges.get(k, []):
        if j == main and all(math.hypot(s[0] - a, s[1] - c) > 8 for a, c in added):
            add_via(*s); added.append(s); union(j, k)
for z, m in MODES:
    z.SetIslandRemovalMode(m)
filler.Fill(b.Zones())
pcbnew.SaveBoard(OUT, b)
print('pieces %d (F %d, B %d), with GND pads %d, unreachable %d; GND stitching vias added: %d -> %s' % (
    N, sum(1 for l, p in nodes if l == F), sum(1 for l, p in nodes if l == B_), len(want), lost, len(added), OUT))
