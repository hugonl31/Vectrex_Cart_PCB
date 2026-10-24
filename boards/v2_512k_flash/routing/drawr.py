"""drawr.py GEOM.json ROUTES.json OUT.png [F|B|FB] - a quick picture of routed tracks over the pads (both layers)"""
import sys, json
from PIL import Image, ImageDraw
geo = json.load(open(sys.argv[1])); rt = json.load(open(sys.argv[2])); out = sys.argv[3]
show = sys.argv[4] if len(sys.argv) > 4 else 'FB'
S = 16                                          # (pixels per mm)
xs = [p[0] for p in geo['outline']]; ys = [p[1] for p in geo['outline']]
X0, Y0 = min(xs) - 1, min(ys) - 1
im = Image.new('RGB', (int((max(xs) - X0 + 1) * S), int((max(ys) - Y0 + 1) * S)), 'white'); d = ImageDraw.Draw(im)
P = lambda x, y: ((x - X0) * S, (y - Y0) * S)
d.polygon([P(*p) for p in geo['outline']], outline=(150, 150, 150))
for h in geo['holes']:
    r = h['d'] / 2 * S; c = P(h['x'], h['y']); d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], outline=(120, 120, 120))
for p in geo['pads']:
    col = (200, 160, 60) if p['tht'] else ((220, 120, 120) if 'F' in p['layers'] else (120, 120, 220))
    for poly in p['poly']:
        d.polygon([P(*q) for q in poly], fill=col)
COL = {'F': (200, 30, 30), 'B': (30, 60, 220)}
for lay in 'BF':
    if lay not in show:
        continue
    for t in rt['stubs'] + rt['tracks']:
        if t['layer'] == lay:
            d.line([P(*q) for q in t['pts']], fill=COL[lay], width=max(1, int(t['w'] * S)))
for v in rt['vias']:
    c = P(v['x'], v['y']); r = 0.38 * S; d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=(20, 140, 20))
im.save(out); print('saved', out, im.size)
