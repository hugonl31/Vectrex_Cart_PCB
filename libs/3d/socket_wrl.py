"""socket_wrl.py OUT.wrl - a simple 3D model of a PLCC-32 through-hole socket (VRML, KiCad's units: 0.1 inch) for the
512K board's renders: a frame around the chip cavity, a thin floor, the 32 pins below. Its own work: free to share.
Size as the usual PLCC-32 THT sockets (e.g. Assmann A-CCS 032-Z-T): about 14.8 x 17.3 mm, 4.2 mm high; the cavity
fits the chip (12.45 x 14.99 mm over its J-leads). Centred on the origin (the footprint places it)."""
import sys

U = 1 / 2.54                      # (mm -> KiCad's VRML units)
OW, OL, H = 14.8, 17.3, 4.2       # outside width (x), length (y), height
IW, IL = 12.9, 15.4               # cavity
FLOOR = 1.2                       # (the chip sits on it)


def box(x0, y0, z0, x1, y1, z1):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return v, f


def shape(boxes, rgb):
    verts, faces = [], []
    for b in boxes:
        v, f = box(*b)
        n = len(verts)
        verts += v
        faces += [tuple(n + i for i in q) for q in f]
    pts = ', '.join('%.4f %.4f %.4f' % (x * U, y * U, z * U) for x, y, z in verts)
    idx = ', '.join('%d, %d, %d, %d, -1' % q for q in faces)
    return ('Shape { appearance Appearance { material Material { diffuseColor %.3f %.3f %.3f specularColor 0.2 0.2 0.2 '
            'shininess 0.3 } } geometry IndexedFaceSet { creaseAngle 0.1 coord Coordinate { point [ %s ] } '
            'coordIndex [ %s ] } }\n' % (rgb + (pts, idx)))


ow, ol, iw, il = OW / 2, OL / 2, IW / 2, IL / 2
frame = [(-ow, -ol, 0, ow, -il, H), (-ow, il, 0, ow, ol, H), (-ow, -il, 0, -iw, il, H), (iw, -il, 0, ow, il, H),
         (-iw, -il, 0, iw, il, FLOOR)]
# the pin-1 corner: a small bevel block marks it (the cavity's corner, as on real sockets)
frame.append((-iw, il - 1.2, FLOOR, -iw + 1.2, il, H - 0.6))
# pins: 2.54 mm grid, two rows per side as the footprint's staggered holes - simple posts under the frame
pins = []
for k in range(-3, 4):                                     # (short sides: x along)
    for y in (-ol + 1.2, ol - 1.2):
        pins.append((k * 1.27 - 0.25, y - 0.25, -3.0, k * 1.27 + 0.25, y + 0.25, 0))
for k in range(-4, 5):                                     # (long sides: y along)
    for x in (-ow + 1.2, ow - 1.2):
        pins.append((x - 0.25, k * 1.27 - 0.25, -3.0, x + 0.25, k * 1.27 + 0.25, 0))
out = '#VRML V2.0 utf8\n# PLCC-32 THT socket, simple model for renders (Vectrex_Cart_PCB)\n'
out += shape(frame, (0.13, 0.13, 0.14)) + shape(pins, (0.85, 0.75, 0.45))
open(sys.argv[1], 'w', newline='\n').write(out)
print('written', sys.argv[1])
