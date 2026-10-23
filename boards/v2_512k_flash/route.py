"""route.py export|import - Freerouting round trip for vectrex-cartridge-512k.kicad_pcb, run with KiCad's Python.
(KiCad's own Specctra export stops on an assertion in this board: this writes the DSN itself.)
  export: board.dsn - outline, keep-outs, every pad (unconnected ones = obstacles), nets, two classes:
          signals 0.254 mm / 0.26 mm clearance, +5V and GND 0.6 mm / 0.27 mm (a little over KiCad's rules); vias 0.762 / 0.508 mm
  import: board.ses (Freerouting's result) -> tracks and vias, GND zones filled, board saved"""
import os, re, sys, pcbnew
HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, 'vectrex-cartridge-512k.kicad_pcb')
UM = lambda v: pcbnew.ToMM(v) * 1000.0
VIA = ('Via762', 762, 508)
SIG = (254, 260)
PWR = (600, 270)
POWER = {'+5V', 'GND'}
TAB = 1600                                      # (um) the top of an edge finger where tracks may join it

def q(s):
    return '"%s"' % s if re.search(r'[\s()"]', s) or s == '' else s

def export(b):
    L = []
    w = L.append
    w('(pcb board.dsn')
    w('  (parser (string_quote ") (space_in_quoted_tokens on) (host_cad "KiCad") (host_version "9"))')
    w('  (resolution um 10)\n  (unit um)')
    w('  (structure')
    w('    (layer F.Cu (type signal) (property (index 0)))\n    (layer B.Cu (type signal) (property (index 1)))')
    ps = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(ps); o = ps.Outline(0)
    pts = [o.CPoint(i) for i in range(o.PointCount())] + [o.CPoint(0)]
    w('    (boundary (path pcb 0 %s))' % ' '.join('%.1f %.1f' % (UM(p.x), -UM(p.y)) for p in pts))
    for z in b.Zones():
        if z.GetIsRuleArea():
            zo = z.Outline().Outline(0)
            zp = [zo.CPoint(i) for i in range(zo.PointCount())] + [zo.CPoint(0)]
            for lay in ('F.Cu', 'B.Cu'):
                if z.IsOnLayer(b.GetLayerID(lay)):
                    w('    (keepout "" (polygon %s 0 %s))' % (lay, ' '.join('%.1f %.1f' % (UM(p.x), -UM(p.y)) for p in zp)))
    # the gold contact area of the edge fingers: no tracks on either side (a track may only meet a finger at its
    # top end), so nothing on the fingers gets scraped by the slot's contacts
    fy1 = min(UM(p.GetPosition().y) - UM(p.GetSize().y if round(p.GetOrientationDegrees()) % 180 == 0 else p.GetSize().x) / 2
              for fp in b.Footprints() if fp.GetReference() == 'CON1' for p in fp.Pads()) / 1000 + TAB / 1000 + 0.05
    fx1, fx2, fy2 = 117.0, 166.5, 137.5
    for lay in ('F.Cu', 'B.Cu'):
        w('    (keepout "" (polygon %s 0 %.1f %.1f %.1f %.1f %.1f %.1f %.1f %.1f %.1f %.1f))' % (
            lay, fx1 * 1000, -fy1 * 1000, fx2 * 1000, -fy1 * 1000, fx2 * 1000, -fy2 * 1000, fx1 * 1000, -fy2 * 1000, fx1 * 1000, -fy1 * 1000))
    # no vias under the back's parts legend (a via there would cut through the printed text)
    bb = None
    for d in b.GetDrawings():
        if d.GetClass() == 'PCB_TEXT' and d.GetLayer() == pcbnew.B_SilkS:
            r = d.GetBoundingBox()
            bb = r if bb is None else bb.Merge(r) or bb
    if bb:
        m = 600
        x1, y1, x2, y2 = UM(bb.GetLeft()) - m, UM(bb.GetTop()) - m, UM(bb.GetRight()) + m, UM(bb.GetBottom()) + m
        for lay in ('F.Cu', 'B.Cu'):
            w('    (via_keepout "" (polygon %s 0 %.1f %.1f %.1f %.1f %.1f %.1f %.1f %.1f %.1f %.1f))' % (
                lay, x1, -y1, x2, -y1, x2, -y2, x1, -y2, x1, -y1))
        print('legend via keep-out: %.1f-%.1f x %.1f-%.1f mm' % (x1 / 1000, x2 / 1000, y1 / 1000, y2 / 1000))
    w('    (via %s)' % VIA[0])
    w('    (rule (width %d) (clearance %d))' % SIG)
    w('  )')
    stacks = {}
    images = []
    place = []
    netpins = {}
    for fp in b.Footprints():
        pads = list(fp.Pads())
        if not pads:
            continue
        ref = fp.GetReference(); img = 'IMG_' + ref
        cx, cy = fp.GetPosition().x, fp.GetPosition().y
        pins = []
        for k, p in enumerate(pads):
            sx, sy = UM(p.GetSize().x), UM(p.GetSize().y)
            if round(p.GetOrientationDegrees()) % 180 == 90:
                sx, sy = sy, sx
            px, py = UM(p.GetPosition().x), UM(p.GetPosition().y)
            if ref == 'CON1':                       # an edge finger: only its top end (TAB um) can take a track
                py = py - sy / 2 + TAB / 2; sy = TAB
            lays = [l for l, lid in (('F.Cu', pcbnew.F_Cu), ('B.Cu', pcbnew.B_Cu)) if p.IsOnLayer(lid)]
            shp = p.GetShape()
            parts = []
            for l in lays:
                if shp == pcbnew.PAD_SHAPE_CIRCLE:
                    parts.append('(shape (circle %s %.1f))' % (l, sx))
                elif shp == pcbnew.PAD_SHAPE_OVAL and abs(sx - sy) > 1:
                    r = min(sx, sy); d = (max(sx, sy) - r) / 2
                    seg = (0, -d, 0, d) if sy > sx else (-d, 0, d, 0)
                    parts.append('(shape (path %s %.1f %.1f %.1f %.1f %.1f))' % ((l, r) + seg))
                else:
                    parts.append('(shape (rect %s %.1f %.1f %.1f %.1f))' % (l, -sx / 2, -sy / 2, sx / 2, sy / 2))
            key = ' '.join(parts)
            name = stacks.setdefault(key, 'PS%d' % len(stacks))
            pin = p.GetNumber() or 'NP%d' % k
            if any(pin == x[1] for x in pins):
                pin = '%s_%d' % (pin, k)
            pins.append((name, pin, px - UM(cx), -(py - UM(cy))))
            if p.GetNetname():
                netpins.setdefault(p.GetNetname(), []).append('%s-%s' % (ref, pin))
        images.append('    (image %s\n%s\n    )' % (img, '\n'.join('      (pin %s %s %.1f %.1f)' % (s, q(n), x, y) for s, n, x, y in pins)))
        place.append('    (component %s (place %s %.1f %.1f front 0))' % (img, q(ref), UM(cx), -UM(cy)))
    w('  (placement\n%s\n  )' % '\n'.join(place))
    w('  (library\n%s' % '\n'.join(images))
    for key, name in stacks.items():
        w('    (padstack %s %s (attach off))' % (name, key))
    w('    (padstack %s (shape (circle F.Cu %d)) (shape (circle B.Cu %d)) (attach off))' % (VIA[0], VIA[1], VIA[1]))
    w('  )')
    w('  (network')
    for n, pl in sorted(netpins.items()):
        w('    (net %s (pins %s))' % (q(n), ' '.join(pl)))
    sig = [q(n) for n in sorted(netpins) if n not in POWER]
    pwr = [q(n) for n in sorted(netpins) if n in POWER]
    w('    (class signal %s (circuit (use_via %s)) (rule (width %d) (clearance %d)))' % ((' '.join(sig), VIA[0]) + SIG))
    w('    (class power %s (circuit (use_via %s)) (rule (width %d) (clearance %d)))' % ((' '.join(pwr), VIA[0]) + PWR))
    w('  )\n  (wiring)\n)')
    open(os.path.join(HERE, 'board.dsn'), 'w').write('\n'.join(L) + '\n')
    print('dsn: %d components, %d nets, %d padstacks' % (len(place), len(netpins), len(stacks)))

def tokens(s):
    return re.findall(r'"[^"]*"|\(|\)|[^\s()]+', s)

def parse(tok, i=0):
    out = []
    while i < len(tok):
        t = tok[i]
        if t == '(':
            sub, i = parse(tok, i + 1); out.append(sub)
        elif t == ')':
            return out, i + 1
        else:
            out.append(t.strip('"')); i += 1
    return out, i

def find(tree, key):
    for x in tree:
        if isinstance(x, list):
            if x and x[0] == key:
                yield x
            yield from find(x, key)

def do_import(b):
    tree, _ = parse(tokens(open(os.path.join(HERE, 'board.ses')).read()))
    res = next(find(tree, 'resolution'))
    scale = 1.0 / float(res[2])                       # SES units -> um
    to = lambda v: pcbnew.FromMM(float(v) * scale / 1000.0)
    for t in list(b.Tracks()):
        b.Remove(t)
    nt = nv = 0
    for net in find(tree, 'net'):
        if len(net) < 2 or not isinstance(net[1], str):
            continue
        ni = b.FindNet(net[1])
        for x in net[2:]:
            if not isinstance(x, list):
                continue
            if x[0] == 'wire':
                path = next(find(x, 'path'))
                lay, width, coords = path[1], float(path[2]), path[3:]
                ptsl = [(to(coords[i]), -to(coords[i + 1])) for i in range(0, len(coords) - 1, 2)]
                for (x1, y1), (x2, y2) in zip(ptsl, ptsl[1:]):
                    t = pcbnew.PCB_TRACK(b); t.SetStart(pcbnew.VECTOR2I(x1, y1)); t.SetEnd(pcbnew.VECTOR2I(x2, y2))
                    t.SetWidth(pcbnew.FromMM(width * scale / 1000.0)); t.SetLayer(b.GetLayerID(lay)); t.SetNet(ni)
                    b.Add(t); nt += 1
            elif x[0] == 'via':
                v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(to(x[2]), -to(x[3])))
                v.SetFrontWidth(pcbnew.FromMM(VIA[1] / 1000.0)); v.SetDrill(pcbnew.FromMM(VIA[2] / 1000.0))
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(ni); b.Add(v); nv += 1
    filler = pcbnew.ZONE_FILLER(b)
    filler.Fill(b.Zones())
    pcbnew.SaveBoard(PCB, b)
    print('imported %d track segments, %d vias; zones filled; saved' % (nt, nv))

b = pcbnew.LoadBoard(PCB)
export(b) if sys.argv[1] == 'export' else do_import(b)
