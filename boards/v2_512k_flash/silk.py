"""silk.py - silkscreen labels (KiCad's Python): on the front only the references next to every part to be
soldered (U1-U4, R1, C1-C4, JP2) and the board version; on the back the parts legend - what goes where."""
import os, pcbnew
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vectrex-cartridge-512k.kicad_pcb')
b = pcbnew.LoadBoard(P)
MM = pcbnew.FromMM
FPS = list(b.Footprints())                          # (read before anything is removed)
MINE = ('SST39', '74HC', 'WE ', '512K', 'R1 ', '1-2 PROT', 'PARTS', 'U1 ', 'U2 ', 'U3 ', 'U4 ', 'C1-C3', 'C1-C4', 'JP2 ', '   ', 'A15=', 'Bank')

def text(s, x, y, size=0.8, rot=0, layer=pcbnew.F_SilkS, just=0):
    t = pcbnew.PCB_TEXT(b); t.SetText(s); t.SetLayer(layer)
    t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size))); t.SetTextThickness(MM(size * 0.15))
    t.SetTextAngleDegrees(rot)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    if just:
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    b.Add(t)

# front: the references, next to their parts (x, y, rotation)
REFS = {'U1': None, 'U2': None, 'U3': None, 'JP2': None,               # (the footprint's own place)
        'U4': (119.6, 106.5, 0), 'R1': (141.7, 86.7, 0), 'C1': (155.1, 113.2, 90),
        'C2': (128.0, 107.5, 90), 'C3': (159.6, 104.4, 90), 'C4': (116.2, 112.2, 90)}
for fp in FPS:
    r = fp.GetReference()
    if r in REFS:
        ref = fp.GetFieldByName('Reference'); ref.SetVisible(True); ref.SetLayer(pcbnew.F_SilkS)
        ref.SetTextSize(pcbnew.VECTOR2I(MM(0.9), MM(0.9))); ref.SetTextThickness(MM(0.15))
        if REFS[r]:
            x, y, rot = REFS[r]
            ref.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y))); ref.SetTextAngleDegrees(rot)
OLD = [d for d in b.GetDrawings() if d.GetClass() == 'PCB_TEXT' and d.GetText().startswith(MINE)]
for d in OLD:                                       # (after the footprints: a removal breaks their objects)
    b.Remove(d)
text('512K CART v2.0', 141.7, 113.6, 0.8)

# back: the parts legend (mirrored text, read from the back; it sits behind the front's left side)
LEGEND = ['PARTS (front side)',
          'U1 SST39SF040 512KB',
          '   in PLCC-32 socket',
          'U2 74HC377  SOIC-20',
          'U3 74HC00   SOIC-14',
          'U4 74HC1G32 SOT23',
          'R1 3.3K     1206',
          'C1-C4 100nF 1206',
          'JP2 1-2 saves (default)',
          '    2-3 write-protect',
          'A15=PB6 A16-18=U2',
          'Bank: write $0000-3FFF']
for i, line in enumerate(LEGEND):
    text(line, 130.4, 91.2 + i * 1.45, 0.8, 0, pcbnew.B_SilkS, 1)
pcbnew.SaveBoard(P, b)
print('labels done')
