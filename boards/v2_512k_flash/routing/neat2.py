"""neat2.py GEOM.json PLAN.json OUT.json - neat.py with rip-up and retry: jobs marked fixed stay; when another job
can not get through, the flexible nets in its way are taken up, it is routed, and they go again.
(neat.py: - a small router for a clean look: tracks only in 0 / 45 / 90 degree directions,
direction changes only in 45 degree steps with a straight piece between them (no sharp 90 degree corners), every bend
costs extra (fewest bends win), vias cost a lot (tracks stay on their layer), and nets go in the plan's order so a bus
lies down lane by lane, each next to the one before. Clearances to all other copper, the board edge, holes, the logos
and the band above the edge fingers; no vias under the back's text block. Grid 0.127 mm."""
import sys, json, math, heapq
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

G, PLAN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
geo = json.load(open(G)); plan = json.load(open(PLAN))
R = 0.127                                       # (mm per cell)
CFG = plan.get('cfg', {})
W_SIG, W_PWR = CFG.get('w_sig', 0.254), CFG.get('w_pwr', 0.5)
CL_SIG, CL_PWR = CFG.get('cl_sig', 0.2), CFG.get('cl_pwr', 0.26)
MARGIN = CFG.get('margin', 0.04)
PAD_EXTRA = CFG.get('pad_extra', 0.0)                # (for the grid's rounding)
EDGE = 0.5; HOLE = 0.3
VIA_D, VIA_DRILL = 0.762, 0.508
BEND = CFG.get('bend', 10.0)                    # (cost of a 45 degree bend, in cells)
VIA_COST = CFG.get('via', 250.0)
KMIN = CFG.get('kmin', 4)                       # (straight cells between two bends)
POWER = set(CFG.get('power', ['+5V', 'GND']))

# ---- the grid: x0 / y0 so that the socket's 2.54 mm grid and the fingers fall on cells
xs = [p[0] for p in geo['outline']]; ys = [p[1] for p in geo['outline']]
ax, ay = CFG.get('align', [134.08, 96.12])
X0 = ax - R * math.ceil((ax - min(xs) + 1) / R); Y0 = ay - R * math.ceil((ay - min(ys) + 1) / R)
NX = int((max(xs) - X0 + 1) / R) + 1; NY = int((max(ys) - Y0 + 1) / R) + 1
cx = lambda x: int(round((x - X0) / R)); cy = lambda y: int(round((y - Y0) / R))
gx = lambda i: X0 + i * R; gy = lambda j: Y0 + j * R
L = 2
nets = sorted({p['net'] for p in geo['pads'] if p['net']})
NID = {n: k + 1 for k, n in enumerate(nets)}
# owner: 0 free, -1 nobody, k only net k (within its clearance); core: copper itself (net id), for reaching targets
owner = np.zeros((L, NY, NX), np.int32)
owner_p = np.zeros((L, NY, NX), np.int32)       # (the same, for a power track's wider clearance)
core = np.zeros((L, NY, NX), np.int32)
noVia = np.zeros((NY, NX), bool)

def raster(polylist, buf=0.0):
    im = Image.new('L', (NX, NY), 0); d = ImageDraw.Draw(im)
    for poly in polylist:
        d.polygon([((x - X0) / R, (y - Y0) / R) for x, y in poly], fill=1)
    m = np.array(im, bool)
    if buf > 0:
        m = ndimage.distance_transform_edt(~m) * R <= buf
    return m

SUB = 5                                          # (pads: their clearance on a 5x finer grid, exact to ~0.02 mm)
def raster_fine(polylist, buf):
    """cells whose centre is within buf (mm) of the polygons' copper, measured on a SUB x finer grid"""
    xs_ = [x for poly in polylist for x, y in poly]; ys_ = [y for poly in polylist for x, y in poly]
    pad_ = buf + 2 * R
    i0 = max(0, int(math.floor((min(xs_) - pad_ - X0) / R))); i1 = min(NX - 1, int(math.ceil((max(xs_) + pad_ - X0) / R)))
    j0 = max(0, int(math.floor((min(ys_) - pad_ - Y0) / R))); j1 = min(NY - 1, int(math.ceil((max(ys_) + pad_ - Y0) / R)))
    w, h = (i1 - i0 + 1) * SUB, (j1 - j0 + 1) * SUB
    r = R / SUB
    ox, oy = X0 + i0 * R - (SUB // 2) * r, Y0 + j0 * R - (SUB // 2) * r   # (fine pixel k*SUB+SUB//2 = coarse centre)
    im = Image.new('L', (w, h), 0); d = ImageDraw.Draw(im)
    for poly in polylist:
        d.polygon([((x - ox) / r, (y - oy) / r) for x, y in poly], fill=1)
    m = np.array(im, bool)
    dist = ndimage.distance_transform_edt(~m) * r
    sub = dist[SUB // 2::SUB, SUB // 2::SUB][:j1 - j0 + 1, :i1 - i0 + 1]
    out = np.zeros((NY, NX), bool)
    out[j0:j0 + sub.shape[0], i0:i0 + sub.shape[1]] = sub <= buf
    return out

def mark(layer, mask, nid, which=(owner, owner_p)):
    for arr in which:
        a = arr[layer]
        if nid < 0:
            a[mask] = -1
        else:
            free = mask & (a == 0); a[free] = nid
            clash = mask & (a > 0) & (a != nid); a[clash] = -1

def disk(r):
    k = int(math.ceil(r / R)); yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
    return (xx * xx + yy * yy) * R * R <= r * r

# ---- static obstacles
inside = raster([geo['outline']])
for l in range(L):
    edge = ndimage.distance_transform_edt(inside) * R
    for arr, w in ((owner, W_SIG), (owner_p, W_PWR)):
        arr[l][edge <= EDGE + w / 2 + MARGIN] = -1
for h in geo['holes']:
    m = np.zeros((NY, NX), bool); m[cy(h['y']), cx(h['x'])] = True
    dist = ndimage.distance_transform_edt(~m) * R
    for l in range(L):
        owner[l][dist <= h['d'] / 2 + HOLE + W_SIG / 2 + MARGIN] = -1
        owner_p[l][dist <= h['d'] / 2 + HOLE + W_PWR / 2 + MARGIN] = -1
    noVia |= dist <= h['d'] / 2 + HOLE + VIA_D / 2 + MARGIN
lx1, ly1, lx2, ly2 = geo['logo']
for l in range(L):
    owner[l][:cy(ly2 + 0.3), :] = -1; owner_p[l][:cy(ly2 + 0.3), :] = -1
if geo['legend']:
    a, b_, c, d = geo['legend']; noVia[cy(b_) - 4:cy(d) + 5, cx(a) - 4:cx(c) + 5] = True
for r in geo['rules']:
    m = raster(r['poly'], W_PWR / 2 + 0.2)
    for ln in r['layers']:
        l = 0 if ln == 'F' else 1
        if r['tracks']:
            owner[l][m] = -1; owner_p[l][m] = -1
    if r['vias']:
        noVia |= m
# the band above the fingers: nothing but the stubs
fing = geo['fingers']
stub_len = CFG.get('stub', 3.0)
ftop = min(f['top'] for f in fing)
stub_top = gy(cy(ftop - stub_len))              # (on the grid)
bx1 = min(f['x'] for f in fing) - 1.5; bx2 = max(f['x'] for f in fing) + 1.5
band = np.zeros((NY, NX), bool); band[cy(stub_top) + 3:, cx(bx1):cx(bx2) + 1] = True
for l in range(L):
    owner[l][band] = -1; owner_p[l][band] = -1
noVia |= np.roll(band, -6, axis=0)

# ---- pads
padcore = {}
for p in geo['pads']:
    nid = NID.get(p['net'], -1)
    m = raster(p['poly'])
    padcore[(p['ref'], p['pad'])] = m
    pw = p['net'] in POWER
    for ln in p['layers']:
        l = 0 if ln == 'F' else 1
        if nid > 0:
            core[l][m] = nid
        cl = max(CL_PWR if pw else CL_SIG, CL_SIG) + PAD_EXTRA     # (pads: a little more - their round shapes on the grid)
        mark(l, raster_fine(p['poly'], cl + W_SIG / 2 + MARGIN), nid, (owner,))
        mark(l, raster_fine(p['poly'], max(cl, CL_PWR) + W_PWR / 2 + MARGIN), nid, (owner_p,))
    if p['tht']:
        m2 = raster(p['poly'], 0.25 + VIA_D / 2 + MARGIN)
        noVia |= m2
    else:
        noVia |= raster(p['poly'], 0.2 + VIA_D / 2 + MARGIN)

# ---- fixed stubs (copper from the finger's top end up to stub_top)
stubs = []
padcount = {}
for p in geo['pads']:
    if p['net']:
        padcount[p['net']] = padcount.get(p['net'], 0) + 1
for f in fing:                                   # (only fingers that lead somewhere get a stub)
    if not f['net'] or padcount.get(f['net'], 0) < 2:
        continue
    l = 0 if f['layer'] == 'F' else 1
    w = W_PWR if f['net'] in POWER else W_SIG
    seg = [(f['x'], f['top'] + 0.8), (f['x'], stub_top)]
    stubs.append({'net': f['net'], 'layer': f['layer'], 'w': w, 'pts': seg, 'x': f['x']})

DIRS = [(1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1)]

JOBG = np.full((L, NY, NX), -1, np.int32)

def add_track(l, pts, w, nid, jid=-1):
    """the copper of a routed polyline (mm) into core / owner"""
    im = Image.new('L', (NX, NY), 0); d = ImageDraw.Draw(im)
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        d.line([((x1 - X0) / R, (y1 - Y0) / R), ((x2 - X0) / R, (y2 - Y0) / R)], fill=1, width=max(1, int(round(w / R))))
    m = np.array(im, bool)
    core[l][m] = nid
    dist = ndimage.distance_transform_edt(~m) * R
    pw = nets[nid - 1] in POWER
    cl = CL_PWR if pw else CL_SIG
    reg = dist <= max(cl, CL_PWR) + W_PWR / 2 + MARGIN + R / 2
    mark(l, dist <= max(cl, CL_SIG) + W_SIG / 2 + MARGIN + R / 2, nid, (owner,))
    mark(l, reg, nid, (owner_p,))
    if jid >= 0:
        JOBG[l][reg] = jid

def add_via(x, y, nid, jid=-1):
    m = np.zeros((NY, NX), bool); m[cy(y), cx(x)] = True
    dist = ndimage.distance_transform_edt(~m) * R
    for l in range(L):
        core[l][dist <= VIA_D / 2] = nid
        mark(l, dist <= VIA_D / 2 + CL_SIG + W_SIG / 2 + MARGIN, nid, (owner,))
        mark(l, dist <= VIA_D / 2 + CL_PWR + W_PWR / 2 + MARGIN, nid, (owner_p,))
        if jid >= 0:
            JOBG[l][dist <= VIA_D / 2 + CL_PWR + W_PWR / 2 + MARGIN] = jid
    noVia[dist <= VIA_D + 0.25] = True

for s in stubs:
    add_track(0 if s['layer'] == 'F' else 1, s['pts'], s['w'], NID[s['net']])
FIXED = []
for ft in plan.get('fixed', []):
    pts = [(x, stub_top if y == 'stub_top' else y) for x, y in ft['pts']]
    add_track(0 if ft['layer'] == 'F' else 1, pts, ft['w'], NID[ft['net']])
    FIXED.append(dict(ft, pts=pts))

VD = disk(VIA_D / 2 + CL_SIG + MARGIN)
STATIC = (owner.copy(), owner_p.copy(), core.copy(), noVia.copy())

def via_ok(i, j, nid, grid=None):
    nv = noVia if grid is None else STATIC[3]      # (relaxed: only fixed copper's via room counts)
    grid = owner if grid is None else grid
    if nv[j, i]:
        return False
    k = VD.shape[0] // 2
    if j - k < 0 or i - k < 0 or j + k >= NY or i + k >= NX:
        return False
    for l in range(L):
        win = grid[l][j - k:j + k + 1, i - k:i + k + 1][VD]   # (the via's copper + clearance: free or own net)
        if np.any((win != 0) & (win != nid)):
            return False
    return True

RELAX_P = 40.0
def route(nid, starts, targets, power=False, layers_ok=(0, 1), first_dir=None, first_k=None, relax=None):
    """A* over (layer, dir, k, y, x). starts: [(l, i, j)]; targets: bool mask per layer (L, NY, NX).
    relax: the grids where only fixed copper counts (other flexible nets: passable at RELAX_P a cell)"""
    own = owner_p if power else owner
    free = [(own[l] == 0) | (own[l] == nid) for l in range(L)]
    pen = None
    if relax is not None:
        rs = relax[1] if power else relax[0]
        sfree = [(rs[l] == 0) | (rs[l] == nid) for l in range(L)]
        pen = [sfree[l] & ~free[l] for l in range(L)]
        free = sfree
    ty, tx = np.nonzero(targets[0] | targets[1])
    if len(tx) == 0:
        return None
    tbx = (tx.min(), tx.max(), ty.min(), ty.max())
    def h(i, j):
        dx = max(tbx[0] - i, 0, i - tbx[1]); dy = max(tbx[2] - j, 0, j - tbx[3])
        return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)
    K = KMIN
    g = {}
    pq = []; cnt = 0
    for (l, i, j) in starts:
        for d in (range(8) if first_dir is None else [first_dir]):
            st = (l, d, K if first_k is None else first_k, j, i)
            g[st] = 0.0; heapq.heappush(pq, (h(i, j), cnt, st, None)); cnt += 1
    prev = {}
    best = None; seen = 0
    while pq:
        f, _, st, par = heapq.heappop(pq)
        l, d, k, j, i = st
        gc = g.get(st)
        if gc is None or f - h(i, j) > gc + 1e-9:
            continue
        seen += 1
        if seen > CFG.get('max_expand', 2500000):
            break
        if targets[l][j, i]:
            best = st; break
        # moves: straight on, or a 45 degree bend (only after KMIN straight cells)
        for nd, bend in ((d, 0), ((d + 1) % 8, 1), ((d - 1) % 8, 1)):
            if bend and k < K:
                continue
            dx, dy = DIRS[nd]; ni, nj = i + dx, j + dy
            if not (0 <= ni < NX and 0 <= nj < NY) or not free[l][nj, ni]:
                continue
            if dx and dy and not (free[l][j, ni] and free[l][nj, i]):
                continue
            step = 1.4142 if dx and dy else 1.0
            if pen is not None and pen[l][nj, ni]:
                step += RELAX_P
            nk = 1 if bend else min(k + 1, K)
            ns = (l, nd, nk, nj, ni)
            ngc = gc + step + (BEND if bend else 0)
            if ngc < g.get(ns, 1e18):
                g[ns] = ngc; prev[ns] = st
                heapq.heappush(pq, (ngc + h(ni, nj), cnt, ns, st)); cnt += 1
        # a via: to the other layer, any direction after it
        if len(layers_ok) > 1 and k >= K:
            ol = 1 - l
            if ol in layers_ok and free[ol][j, i] and via_ok(i, j, nid, None if relax is None else relax[0]):
                ns = (ol, d, K, j, i)
                ngc = gc + VIA_COST
                if ngc < g.get(ns, 1e18):
                    g[ns] = ngc; prev[ns] = st
                    heapq.heappush(pq, (ngc + h(i, j), cnt, ns, st)); cnt += 1
    if best is None:
        return None
    path = [best]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    return path, seen

def to_polylines(path):
    """[(layer, [(x, y) ...])], vias [(x, y)]"""
    out, vias = [], []
    cur_l = path[0][0]; pts = [(path[0][4], path[0][3])]
    last_dir = None
    for a, bst in zip(path, path[1:]):
        if bst[0] != a[0]:
            if pts[-1] != (a[4], a[3]):                    # (the piece ends at the via: its last straight run)
                pts.append((a[4], a[3]))
            out.append((cur_l, pts)); vias.append((a[4], a[3]))
            cur_l = bst[0]; pts = [(bst[4], bst[3])]; last_dir = None
            continue
        dxy = (bst[4] - a[4], bst[3] - a[3])
        if last_dir is not None and dxy != last_dir:
            pts.append((a[4], a[3]))
        last_dir = dxy
    pts.append((path[-1][4], path[-1][3]))
    out.append((cur_l, pts))
    conv = lambda P: [(round(gx(i), 4), round(gy(j), 4)) for i, j in P]
    return [(l, conv(p)) for l, p in out if len(p) >= 2 and p[0] != p[-1]], [(round(gx(i), 4), round(gy(j), 4)) for i, j in vias]

# ---------------------------------------------------------------- jobs, with rip-up and retry
from collections import deque
pads_by_net = {}
for p in geo['pads']:
    if p['net']:
        pads_by_net.setdefault(p['net'], []).append(p)
pad_cells = lambda p: padcore[(p['ref'], p['pad'])]
JOBS = plan['jobs']
NFIX = plan.get('nfixed', 0)                      # (the first NFIX jobs stay where they are)

def plan_job(ji, relax=None):
    job = JOBS[ji]
    net = job['net']; nid = NID[net]; pw = net in POWER
    f = None
    if 'from_finger' in job:
        f = [s for s in stubs if s['net'] == net and abs(s['x'] - job['from_finger']) < 0.05][0]
        starts = [(0 if f['layer'] == 'F' else 1, cx(f['x']), cy(stub_top))]; first = 2
    else:
        p = [q for q in pads_by_net[net] if '%s.%s' % (q['ref'], q['pad']) == job['from']][0]
        starts = [(0 if ln == 'F' else 1, cx(p['x']), cy(p['y'])) for ln in p['layers']]; first = None
    tg = np.zeros((L, NY, NX), bool)
    if 'to' in job:
        for t in job['to']:
            q = [x for x in pads_by_net[net] if '%s.%s' % (x['ref'], x['pad']) == t][0]
            for ln in q['layers']:
                tg[0 if ln == 'F' else 1] |= pad_cells(q)
    else:
        for l in range(L):
            tg[l] = core[l] == nid
        if 'from' in job:
            for ln in p['layers']:
                tg[0 if ln == 'F' else 1] &= ~pad_cells(p)
        # only copper already joined to the net's routed part: not a pad (or a finger's stub) nobody reached yet
        con, fing_on = set(), False
        for k in routed:
            jk = JOBS[k]
            if jk['net'] != net:
                continue
            if 'from' in jk: con.add(jk['from'])
            con.update(jk.get('to', []))
            if 'from_finger' in jk: fing_on = True
        for q in pads_by_net[net]:
            key = '%s.%s' % (q['ref'], q['pad'])
            if q['ref'] == 'CON1':
                if fing_on:
                    continue
                sl = 0 if q['layers'][0] == 'F' else 1
                tg[sl][:, max(0, cx(q['x']) - 6):cx(q['x']) + 7] &= ~np.arange(NY)[:, None].__ge__(cy(stub_top) - 2)
                tg[sl] &= ~pad_cells(q)
            elif key not in con:
                for ln in q['layers']:
                    tg[0 if ln == 'F' else 1] &= ~pad_cells(q)
        if f is not None:
            sl = 0 if f['layer'] == 'F' else 1
            tg[sl][:, max(0, cx(f['x']) - 6):cx(f['x']) + 7] &= ~np.arange(NY)[:, None].__ge__(cy(stub_top) - 2)
            for q in [q for q in pads_by_net[net] if q['ref'] == 'CON1' and abs(q['x'] - f['x']) < 0.05]:
                tg[sl] &= ~pad_cells(q)
        if not tg.any():
            return None
    lays = tuple(job.get('layers', (0, 1)))
    legs = list(job.get('wp', []))
    full = []; seen = 0; fk = None
    for leg in range(len(legs) + 1):
        if leg < len(legs):
            wx_, wy_ = legs[leg]
            tgl = np.zeros((L, NY, NX), bool); rr = int(job.get('wp_r', 0.13) / R) + 1
            for l in lays:
                tgl[l][max(0, cy(wy_) - rr):cy(wy_) + rr + 1, max(0, cx(wx_) - rr):cx(wx_) + rr + 1] = True
        else:
            tgl = tg
        r = route(nid, starts, tgl, pw, lays, first, fk, relax)
        if r is None and leg > 0:
            r = route(nid, starts, tgl, pw, lays, None, None, relax)
        if r is None:
            return None
        path, sn = r; seen += sn
        full += path if not full else path[1:]
        end = path[-1]; starts = [(end[0], end[4], end[3])]; first = end[1]; fk = end[2]
    polys, vias = to_polylines(full)
    return polys, vias, seen, full

routed = {}                                        # job -> (polys, vias)

def commit(ji, polys, vias):
    job = JOBS[ji]; nid = NID[job['net']]; pw = job['net'] in POWER
    w = job.get('w', W_PWR if pw else W_SIG)
    for l, pts in polys:
        add_track(l, pts, w, nid, ji if ji >= NFIX else -1)
    for v in vias:
        add_via(v[0], v[1], nid, ji if ji >= NFIX else -1)
    routed[ji] = (polys, vias)

def rebuild():
    for arr, st in zip((owner, owner_p, core, noVia), STATIC):
        arr[...] = st
    JOBG[...] = -1
    for ji in sorted(routed):
        polys, vias = routed.pop(ji)
        commit(ji, polys, vias)

relaxg = None
queue = deque(range(len(JOBS))); rips = {}; steps = 0; failed = set()
while queue and steps < CFG.get('max_steps', 600):
    ji = queue.popleft(); steps += 1
    if ji == NFIX and relaxg is None:              # (the fixed jobs are in: only they block a relaxed search)
        relaxg = (owner.copy(), owner_p.copy())
    if ji < NFIX and relaxg is None and ji == NFIX:
        pass
    job = JOBS[ji]
    r = plan_job(ji)
    if r is not None:
        commit(ji, r[0], r[1]); failed.discard(ji)
        print('%-8s %-14s %3d bends %d vias' % (job['net'], job.get('from', job.get('from_finger')),
                                               sum(len(p) - 2 for l, p in r[0]), len(r[1])), flush=True)
        continue
    if ji < NFIX or relaxg is None:
        failed.add(ji); print('FAILED (fixed)', job['net'], flush=True); continue
    # who is in the way: a search through the flexible nets' room
    rr = plan_job(ji, relaxg)
    blockers = set()
    if rr is not None:
        for (l, d, k, j, i) in rr[3]:
            g = JOBG[l][j, i]
            if g >= NFIX and JOBS[g]['net'] != job['net']:
                blockers.add(JOBS[g]['net'])
    blockers = {n for n in blockers if rips.get(n, 0) < CFG.get('max_rips', 5)}
    if not blockers:
        failed.add(ji); print('FAILED', job['net'], job.get('from', job.get('from_finger')), flush=True); continue
    for n in blockers:
        rips[n] = rips.get(n, 0) + 1
    gone = sorted(k for k in routed if JOBS[k]['net'] in blockers)
    for k in gone:
        routed.pop(k)
    rebuild()
    print('  rip up %s for %s (%d jobs)' % (sorted(blockers), job['net'], len(gone)), flush=True)
    queue.appendleft(ji)
    for k in gone:
        queue.append(k)

result = {'stubs': stubs, 'tracks': list(FIXED), 'vias': [], 'failed': [JOBS[k] for k in sorted(failed)], 'stub_top': stub_top}
for ji in sorted(routed):
    job = JOBS[ji]; pw = job['net'] in POWER; w = job.get('w', W_PWR if pw else W_SIG)
    polys, vias = routed[ji]
    for l, pts in polys:
        result['tracks'].append({'net': job['net'], 'layer': 'FB'[l], 'w': w, 'pts': pts})
    for v in vias:
        result['vias'].append({'net': job['net'], 'x': v[0], 'y': v[1], 'power': pw})
missing = [JOBS[k] for k in range(len(JOBS)) if k not in routed and k not in failed]
result['failed'] += missing
json.dump(result, open(OUT, 'w'), indent=0)
print('routed %d of %d jobs, failed %d, steps %d, vias %d' % (len(routed), len(JOBS), len(result['failed']), steps, len(result['vias'])))
