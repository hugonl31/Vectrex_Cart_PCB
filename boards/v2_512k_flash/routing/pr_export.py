"""pr_export.py BOARD OUT.json - everything the neat router needs from a KiCad board: outline, holes, pads (copper
polygons, net, layers), rule areas, the back's text block (no vias there), the edge fingers. Run with KiCad's Python."""
import sys, json
try:
    import wx; wx.DisableAsserts()
except Exception:
    pass
import pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
mm = lambda v: round(pcbnew.ToMM(v), 4)

def polys(ps):
    out = []
    for i in range(ps.OutlineCount()):
        o = ps.Outline(i)
        out.append([(mm(o.CPoint(k).x), mm(o.CPoint(k).y)) for k in range(o.PointCount())])
    return out

D = {'pads': [], 'holes': [], 'rules': [], 'fingers': []}
o = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(o)
D['outline'] = polys(o)[0]
LAYERS = ((pcbnew.F_Cu, 'F'), (pcbnew.B_Cu, 'B'))
fps = list(b.Footprints())
for fp in fps:
    ref = fp.GetReference()
    for p in fp.Pads():
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            D['holes'].append({'x': mm(p.GetPosition().x), 'y': mm(p.GetPosition().y), 'd': mm(p.GetDrillSize().x)})
            continue
        lays = [n for l, n in LAYERS if p.IsOnLayer(l)]
        ps = pcbnew.SHAPE_POLY_SET()
        p.TransformShapeToPolygon(ps, pcbnew.F_Cu if 'F' in lays else pcbnew.B_Cu, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
        rec = {'ref': ref, 'pad': p.GetNumber(), 'net': p.GetNetname(), 'layers': lays,
               'x': mm(p.GetPosition().x), 'y': mm(p.GetPosition().y), 'poly': polys(ps),
               'tht': p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH, 'drill': mm(p.GetDrillSize().x)}
        D['pads'].append(rec)
        if ref == 'CON1':
            bb = p.GetBoundingBox()
            D['fingers'].append({'pad': p.GetNumber(), 'net': p.GetNetname(), 'layer': lays[0], 'x': mm(p.GetPosition().x),
                                 'top': mm(bb.GetTop()), 'bottom': mm(bb.GetBottom()), 'w': mm(bb.GetWidth())})
for z in b.Zones():
    if z.GetIsRuleArea():
        D['rules'].append({'layers': [n for l, n in LAYERS if z.IsOnLayer(l)], 'tracks': z.GetDoNotAllowTracks(),
                           'vias': z.GetDoNotAllowVias(), 'poly': polys(z.Outline())})
bx = None
for d in b.GetDrawings():
    if d.GetClass() == 'PCB_TEXT' and d.GetLayer() == pcbnew.B_SilkS:
        r = d.GetBoundingBox(); e = (r.GetLeft(), r.GetTop(), r.GetRight(), r.GetBottom())
        bx = e if bx is None else (min(bx[0], e[0]), min(bx[1], e[1]), max(bx[2], e[2]), max(bx[3], e[3]))
D['legend'] = [mm(v) for v in bx] if bx else None
logo = None
for fp in fps:
    if fp.GetReference() in ('G1', 'G3'):
        r = fp.GetBoundingBox(False, False)
        e = (r.GetLeft(), r.GetTop(), r.GetRight(), r.GetBottom())
        logo = e if logo is None else (min(logo[0], e[0]), min(logo[1], e[1]), max(logo[2], e[2]), max(logo[3], e[3]))
D['logo'] = [mm(v) for v in logo]
json.dump(D, open(sys.argv[2], 'w'), indent=0)
print('pads %d holes %d rules %d fingers %d legend %s logo %s' % (len(D['pads']), len(D['holes']), len(D['rules']),
                                                                 len(D['fingers']), D['legend'], D['logo']))
