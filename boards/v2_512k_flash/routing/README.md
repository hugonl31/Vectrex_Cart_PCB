# Routing the 512K board

The traces of `../vectrex-cartridge-512k.kicad_pcb` come from a small router of our own (`neat2.py`), made for
a clean look: tracks only at 0 / 45 / 90 degrees, a straight run between bends, every bend and every via
costs extra, and the nets are laid in a planned order so a bus lies down lane by lane. Clearances are
checked on a 0.127 mm grid (pads on a 5x finer one). Python 3 with numpy, scipy and Pillow; the KiCad
steps need KiCad 9's Python (`C:\Program Files\KiCad\9.0\bin\python.exe`).

| Step | |
|---|---|
| `make_board.py` (one folder up) | the parts, nets and placement, from the v1 board - no tracks |
| `pr_export.py BOARD geom.json` | KiCad Python: outline, holes, pads, rule areas, fingers -> JSON |
| `neat2.py geom.json plan.json routes.json` | the router; with rip-up and retry of the flexible nets |
| `orders2.py plan.json 13 N PAR TAG geom.json` | tries N orders of the jobs after the 13 fixed bus lanes, PAR at a time; prints the best |
| `pr_import.py BOARD routes.json OUT` | KiCad Python: the routes into the board, loose ends joined, zones filled |
| `stitch.py IN OUT` | KiCad Python: GND stitching vias - every piece of the GND fill tied to the ground |
| `drawr.py geom.json routes.json out.png [F|B]` | a quick picture of the routes |

`plan_rr9.json`: the jobs. The first 13 are the address bus with waypoints (fixed lanes); every finger job
starts with a straight stub up from the finger (only fingers with a function); +5 V fingers 2 and 4 are
bridged by a fixed 0.61 mm track. `cfg`: track widths, clearances, bend / via costs, the grid margin.

Two touches by hand after the last run: one more GND stitching via (118.17, 115.16: a piece of the front fill
round U4 pin 3 and C4 was cut off), and the PB6 track next to R1 moved 0.5 mm with a 45 degree step, to keep the
project's 0.254 mm clearance to the +5 V track (the router ran with 0.2 mm).

Then DRC in KiCad (the project's rules): no unconnected items, no clearance errors; left only the fingers' shared
solder-mask opening (as on v1) and silkscreen notes - see Checks in `../README.md`.
