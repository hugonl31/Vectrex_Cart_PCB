"""orders.py PLAN.json NBUS N PAR TAG - tries N random orders of the plan's jobs after the first NBUS (the bus stays
first), PAR at a time; a net's own jobs keep their order. Prints and saves the best (fewest failed, vias, bends)."""
import json, random, subprocess, sys, os, re
plan_f, nbus, n, par, tag = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
HERE = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(plan_f))
bus, rest = P['jobs'][:nbus], P['jobs'][nbus:]
groups = {}
for j in rest:
    groups.setdefault(j['net'], []).append(j)
procs, results = [], []
def start(k):
    rnd = random.Random(k)
    nets = list(groups); rnd.shuffle(nets)
    jobs = bus + [j for nn in nets for j in groups[nn]]
    pf = os.path.join(HERE, '_ord_%s_%d.json' % (tag, k)); of = os.path.join(HERE, '_ordr_%s_%d.json' % (tag, k))
    json.dump(dict(P, jobs=jobs), open(pf, 'w'))
    lg = open(os.path.join(HERE, '_ord_%s_%d.log' % (tag, k)), 'w')
    return subprocess.Popen([sys.executable, os.path.join(HERE, 'neat2.py'), sys.argv[6] if len(sys.argv) > 6 else 'geom2.json', pf, of],
                            stdout=lg, stderr=subprocess.STDOUT, cwd=HERE), k, of
pending = list(range(n)); running = []
while pending or running:
    while pending and len(running) < par:
        running.append(start(pending.pop(0)))
    for r in list(running):
        if r[0].poll() is not None:
            running.remove(r)
            k, of = r[1], r[2]
            try:
                d = json.load(open(of))
                nv = len(d['vias']); nf = len(d['failed'])
                nb = sum(len(t['pts']) - 2 for t in d['tracks'])
                results.append((nf, nv, nb, k, of)); print('order %d: failed %d vias %d bends %d %s' % (
                    k, nf, nv, nb, [f['net'] for f in d['failed']]), flush=True)
            except Exception as e:
                print('order %d: error %s' % (k, e), flush=True)
    import time; time.sleep(2)
results.sort()
print('BEST', results[0][:4], results[0][4])
