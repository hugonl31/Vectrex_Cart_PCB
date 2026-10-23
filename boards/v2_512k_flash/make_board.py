"""make_board.py - builds vectrex-cartridge-512k.kicad_pcb from the v1 64K board (../v1_27c512_64k/vectrex-cartridge-64k.kicad_pcb) (outline,
edge fingers, logos, mounting holes, GND zone and finger keep-out kept) with the 512 KB flash, the 74HC377 bank latch
and the 74HC00 /OE gate. Run with KiCad's Python: "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" make_board.py

Circuit (see README.md in this folder):
  U1 SST39SF040 (PLCC-32 socket): A0-A14, D0-D7 from the port; A15 = PB6 (as v1); A16/A17/A18 = U2 Q0/Q1/Q2;
     /CE = port 16 (V-CE); /OE = FL_OE (U3); /WE = JP2 (R/W = the game saves into the flash, or +5 V)
  U2 74HC377 (SOIC-20W): D0-D7 = data bus, /E = R/W (port 30), CP = /CART (port 32): a write to the cartridge
     area stores the bank number. Q3-Q7 free.
  U3 74HC00 (SOIC-14): gate A: E = NAND(V-OE, V-OE); gate B: FL_OE = NAND(E, R/W) - the flash drives the bus only
     on reads (with /OE low during a write it may drive it: datasheet table 4-1). Gates C, D: inputs to GND.
  U4 74HC1G32 (SOT-23-5): latch clock = /CART OR A14 - only writes to $0000-$3FFF set the bank, so the flash's
     save commands ($5555 / $2AAA) leave A16-A18 the same for erase and program (see README).
  R1 3.3K pull-up on PB6 (A15 defined from power-on, as v1), C1-C4 100 nF. (No DS2431: saves go into the flash.)
"""
import os, pcbnew
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'v1_27c512_64k', 'vectrex-cartridge-64k.kicad_pcb')
OUT = os.path.join(HERE, 'vectrex-cartridge-512k.kicad_pcb')
LIB = 'C:/Program Files/KiCad/9.0/share/kicad/footprints/'
MM = pcbnew.FromMM

b = pcbnew.LoadBoard(SRC)
fps, zones, tracks = list(b.Footprints()), list(b.Zones()), list(b.Tracks())   # (collected before any removal)
keep, drop = {}, []
for fp in fps:
    name = fp.GetFPIDAsString().split(':')[-1]
    if name.startswith(('28P6_ATM', 'Solder_Jumper', 'DS2431')):
        drop.append(fp)
    elif name.startswith(('R1_', 'C1_')):
        keep[name[:3]] = fp
drop += [z for z in zones if not z.GetIsRuleArea() and z.GetNetname() != 'GND']   # (old copper island at a hole)
drop += tracks                                      # (all new routing)
OLD_SILK = {'27C512', 'R1=3.3K 1206', 'C1=0.1UF 1206', '32KB', '64KB', 'R1', 'C1', 'DS2431+'}
for d in list(b.GetDrawings()):                     # (v1's silkscreen notes and jumper marks)
    if d.GetLayerName() in ('F.Silkscreen', 'F.Mask') and (d.GetClass() == 'PCB_SHAPE' or
                                                          (hasattr(d, 'GetText') and d.GetText() in OLD_SILK)):
        drop.append(d)
for z in zones:
    z.UnFill()                                      # (filled again after routing)
for item in drop:
    b.Remove(item)

nets = {}
def net(name):
    if name not in nets:
        n = b.FindNet(name)
        if n is None:
            n = pcbnew.NETINFO_ITEM(b, name); b.Add(n)
        nets[name] = n
    return nets[name]

def place(fp, ref, value, x, y, rot=0, pads=None):
    fp.SetReference(ref); fp.SetValue(value)
    fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y))); fp.SetOrientationDegrees(rot)
    for p in fp.Pads():
        n = (pads or {}).get(p.GetNumber())
        p.SetNet(net(n) if n else b.FindNet(''))
    if fp.GetParent() is None:
        b.Add(fp)
    return fp

def lib(libname, name):
    return pcbnew.FootprintLoad(LIB + libname + '.pretty', name)

# U1: the flash in its PLCC-32 socket (JEDEC 32-pin numbering)
A = {str(p): 'C_A%d' % a for p, a in ((12, 0), (11, 1), (10, 2), (9, 3), (8, 4), (7, 5), (6, 6), (5, 7), (27, 8),
                                      (26, 9), (23, 10), (25, 11), (4, 12), (28, 13), (29, 14))}
D = {str(p): 'C_D%d' % d for p, d in ((13, 0), (14, 1), (15, 2), (17, 3), (18, 4), (19, 5), (20, 6), (21, 7))}
u1 = dict(A, **D)
u1.update({'1': 'BA18', '2': 'BA16', '3': 'V-PB6', '30': 'BA17', '16': 'GND', '32': '+5V', '22': 'V-CE', '24': 'FL_OE', '31': 'FL_WE'})
place(lib('Package_LCC', 'PLCC-32_THT-Socket'), 'U1', 'SST39SF040 (PLCC-32 socket)', 136.62, 101.2, 90, u1)

# U2: 74HC377 bank latch
u2 = {'1': 'V-RW', '11': 'LCLK', '10': 'GND', '20': '+5V', '2': 'BA16', '5': 'BA17', '6': 'BA18'}
u2.update({str(p): 'C_D%d' % d for p, d in ((3, 0), (4, 1), (7, 2), (8, 3), (13, 4), (14, 5), (17, 6), (18, 7))})
place(lib('Package_SO', 'SOIC-20W_7.5x12.8mm_P1.27mm'), 'U2', '74HC377', 122.6, 98.2, 0, u2)

# U3: 74HC00 - /OE only on reads
u3 = {'1': 'V-OE', '2': 'V-OE', '3': 'E', '4': 'E', '5': 'V-RW', '6': 'FL_OE', '7': 'GND', '14': '+5V',
      '9': 'GND', '10': 'GND', '12': 'GND', '13': 'GND'}
place(lib('Package_SO', 'SOIC-14_3.9x8.7mm_P1.27mm'), 'U3', '74HC00', 162.0, 97.0, 0, u3)

# U4: 74HC1G32 - the latch clock only for the cartridge's lower 16 KB (A14 low)
place(lib('Package_TO_SOT_SMD', 'SOT-23-5'), 'U4', '74HC1G32', 119.6, 108.8, 0,
      {'1': 'V-CART', '2': 'C_A14', '3': 'GND', '4': 'LCLK', '5': '+5V'})
place(keep['R1_'], 'R1', '3.3K', 141.7, 89.0, 0, {'1': 'V-PB6', '2': '+5V'})

# decoupling: C1 flash, C2 latch, C3 gate
c1 = keep['C1_']
place(c1, 'C1', '100nF', 157.5, 113.2, 0, {'1': '+5V', '2': 'GND'})
for ref, x, y, rot in (('C2', 125.5, 107.5, 0), ('C3', 162.0, 104.4, 0), ('C4', 119.6, 112.4, 90)):
    c = pcbnew.Cast_to_FOOTPRINT(c1.Duplicate())
    b.Add(c)
    place(c, ref, '100nF', x, y, rot, {'1': '+5V', '2': 'GND'})

# JP2: flash /WE - pad 1 R/W (the printed bridge 1-2: the game saves into the flash), 2 /WE, 3 +5V (cut 1-2,
# bridge 2-3: write-protected)
jp = lib('Jumper', 'SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm_NumberLabels')
place(jp, 'JP2', 'FLASH /WE', 162.0, 109.6, 90, {'1': 'V-RW', '2': 'FL_WE', '3': '+5V'})

tb = b.GetTitleBlock(); tb.SetTitle('Vectrex Cartridge 512K (bank latch)'); tb.SetRevision('v2.0'); tb.SetDate('2026-10-15')
b.SetTitleBlock(tb)
b.BuildConnectivity()
pcbnew.SaveBoard(OUT, b)
print('saved', OUT, 'nets', len(nets))
