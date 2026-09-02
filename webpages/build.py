#!/usr/bin/env python3
"""Build a self-contained HTML report from the vmem repo's bench/results/ and the mlc baseline.

    python3 build.py && python3 -m http.server 8001 --directory .

Lives in vmem-work/webpages/ (decoupled from the repo). Everything is inlined,
so it serves over a plain ssh -L tunnel.
"""
import re, os, json, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
# repo-local benchmark data now lives in the sibling vmem/ repo
RES  = os.path.join(HERE, '..', 'vmem', 'bench', 'results')
MLC  = os.path.expanduser('~/Projects/mlc/results')
OUT  = os.path.join(HERE, 'index.html')

ANSI = re.compile(r'\x1b\[[0-9;]*m')


def rows(fn):
    """(label, GB/s) for every timed phase in a microbenchmark's stdout."""
    try:
        txt = ANSI.sub('', open(os.path.join(RES, fn), errors='ignore').read())
    except FileNotFoundError:
        return []
    out = []
    for line in txt.splitlines():
        m = re.match(r'\s*(\S[^.]*?)\s*\.{3,}\s*done\..*GB/s:\s*([\d.]+)', line)
        if m:
            out.append((m.group(1).strip(), float(m.group(2))))
    return out


def series(prefix, phase, passes=(1, 2, 3)):
    """Mean/spread of one phase across passes."""
    vals = []
    for p in passes:
        for label, v in rows(f'{prefix}_p{p}.txt'):
            if label.startswith(phase):
                vals.append(v)
                break
    if not vals:
        return None
    return {'mean': round(st.mean(vals), 3),
            'spread': round(max(vals) - min(vals), 3), 'n': len(vals)}


def mlc_copy(fn):
    """src->dst copy matrix from the mlc baseline."""
    try:
        txt = open(os.path.join(MLC, fn)).read()
    except FileNotFoundError:
        return None
    m = [[float(x) for x in r.split()[1:]]
         for r in txt.splitlines() if re.match(r'\s*[01]\s+[\d.]', r)]
    return {'demote': m[0][1], 'promote': m[1][0]} if len(m) == 2 else None


# Hot-set characterization (from ~/Projects/vmem-sweep, sample_period=10000, all
# pages in DRAM, tiering off). Each point is (hot-set size as % of resident
# footprint, cumulative % of LLC misses). Static: the 24-run sweep is complete.
HOTSET = {
    'cov': [50, 80, 90, 95, 98, 99, 100],
    'series': [
        {'k': 'xsbench',  'nm': 'XSBench',  'c': 'hs1', 'hot': 2.7,
         'pts': [[1.7, 50], [2.7, 80], [3.1, 90], [3.6, 95], [28.2, 98], [50.1, 99], [90.5, 100]]},
        {'k': 'pagerank', 'nm': 'PageRank', 'c': 'hs2', 'hot': 0.9,
         'pts': [[0.5, 50], [0.9, 80], [6.9, 90], [15.5, 95], [23.0, 98], [26.7, 99], [35.6, 100]]},
        {'k': 'graph500', 'nm': 'Graph500', 'c': 'hs3', 'hot': 2.3,
         'pts': [[1.3, 50], [2.3, 80], [4.0, 90], [20.3, 95], [35.2, 98], [40.9, 99], [50.9, 100]]},
        {'k': 'amg',      'nm': 'AMG',      'c': 'hs4', 'hot': 5.5,
         'pts': [[0.8, 50], [5.5, 80], [9.7, 90], [13.3, 95], [17.4, 98], [18.8, 99], [20.2, 100]]},
        {'k': 'lulesh',   'nm': 'LULESH',   'c': 'hs5', 'hot': 4.3,
         'pts': [[2.1, 50], [4.3, 80], [5.3, 90], [6.0, 95], [6.6, 98], [6.9, 99], [7.7, 100]]},
        {'k': 'bfs',      'nm': 'BFS',      'c': 'hs6', 'hot': 10.0, 'diffuse': True,
         'pts': [[3.0, 50], [10.0, 80], [12.8, 90], [14.3, 95], [15.1, 98], [15.4, 99], [15.7, 100]]},
    ],
}


# Interval sweep (from ~/Projects/vmem-sweep, sample_period=10000 LOCKED,
# tiering off). Per benchmark, the MEDIAN hottest-page miss count in a single
# analysis window, vs the window length. This is the signal the live policy
# would threshold on: it must clear single digits to separate hot from cold.
# null = no window had enough samples to measure at that interval.
INTERVAL = {
    'ms': [25, 50, 100, 250, 500, 1000, 2500],
    'thresh': 16,   # per-page count a hot/cold threshold needs to sit above
    'series': [
        {'nm': 'PageRank', 'c': 'hs2', 'cls': 'rich',   'sig': [15, 15, 15, 25, 39, 75, 166]},
        {'nm': 'XSBench',  'c': 'hs1', 'cls': 'rich',   'sig': [9, 8, 8, 13, 22, 38, 83]},
        {'nm': 'Graph500', 'c': 'hs3', 'cls': 'rich',   'sig': [8, 10, 10, 12, 18, 31, 68]},
        {'nm': 'AMG',      'c': 'hs4', 'cls': 'sparse', 'sig': [2, 2, 2, 3, 2, 3, 6]},
        {'nm': 'BFS',      'c': 'hs6', 'cls': 'sparse', 'sig': [2, 2, 2, 2, 3, 3, 5]},
        {'nm': 'LULESH',   'c': 'hs5', 'cls': 'sparse', 'sig': [None, None, None, 2, 2, 2, 2]},
    ],
}


# Miss vs access signal, side by side (from ~/Projects/vmem-sweep interval +
# interval_access sweeps). Per benchmark, median per-window hottest-page count
# vs window length, for BOTH the L3-miss event (period 1e4) and the ALL_LOADS
# access event (period 1e5). null = no window had enough samples to measure.
COMPARE = {
    'windows': [25, 50, 100, 250, 500, 1000, 2500],
    'thresh': 16,
    'benches': [
        {'nm': 'XSBench',  'miss': [9, 8, 8, 13, 22, 38, 83],       'access': [7, 7, 7, 13, 23, 44, 99]},
        {'nm': 'PageRank', 'miss': [15, 15, 15, 25, 39, 75, 166],   'access': [15, 17, 17, 40, 79, 145, 349]},
        {'nm': 'Graph500', 'miss': [8, 10, 10, 12, 18, 31, 68],     'access': [11, 18, 18, 38, 69, 129, 293]},
        {'nm': 'AMG',      'miss': [2, 2, 2, 3, 2, 3, 6],           'access': [20, 33, 34, 87, 173, 335, 849]},
        {'nm': 'LULESH',   'miss': [None, None, None, 2, 2, 2, 2],  'access': [9, 16, 17, 41, 83, 163, 381]},
        {'nm': 'BFS',      'miss': [2, 2, 2, 2, 2, 3, 5],           'access': [12, 13, 19, 29, 69, 102, 227]},
    ],
}


# --- Phase-1 placement-ladder figures (next-paper F1/F8), DATA-DRIVEN from the
# vmem-sweep results.tsv so they extend automatically as benchmarks land. Metric
# units differ per benchmark (grind / wall-clock / avg-time), so F1 NORMALIZES each
# condition to that benchmark's all-DRAM. Missing conditions handled gracefully. ---
P1_TSV = os.path.expanduser('~/Projects/vmem-sweep/results/phase1/results.tsv')
FOOT_TSV = os.path.expanduser('~/Projects/vmem-sweep/results/phase1/footprints.tsv')
P1_CONDS = [  # cond key, label, palette var, note
    ('all_dram',    'all-DRAM',        'hs3', 'the ideal floor'),
    ('first_touch', 'first-touch 25%', 'hs4', 'DRAM-first, no tiering'),
    ('vmem_demote', 'VMem demote 25%', 'hs1', 'tuned demotion, promo off'),
    ('all_pmem',    'all-PMEM',        'hs2', 'worst case'),
]
P1_NAMES = {'lulesh': 'LULESH', 'amg': 'AMG', 'gapbs_bfs': 'GAPBS-BFS',
            'gapbs_pr': 'GAPBS-PR', 'snap': 'SNAP', 'qmcpack': 'QMCPACK', 'warpx': 'WarpX'}


def p1_figures(path=P1_TSV):
    raw = {}
    try:
        for line in open(path):
            p = line.split()
            if len(p) == 4 and p[3] != 'CRASH':
                try:
                    raw.setdefault(p[0], {}).setdefault(p[1], []).append(float(p[3]))
                except ValueError:
                    pass
    except FileNotFoundError:
        return []
    fig = []
    for b, conds in raw.items():
        base = st.mean(conds['all_dram']) if 'all_dram' in conds else None
        e = {'key': b, 'name': P1_NAMES.get(b, b), 'bars': []}
        for c, label, col, note in P1_CONDS:
            if c not in conds or not base:
                continue
            xs = conds[c]; m = st.mean(xs)
            ci = 1.96 * st.pstdev(xs) / len(xs) ** 0.5 if len(xs) > 1 else 0
            e['bars'].append({'label': label, 'col': col, 'note': note, 'raw': round(m, 3),
                              'n': len(xs), 'x': round(m / base, 3), 'ci': round(ci / base, 3)})
        pm = st.mean(conds['all_pmem']) if 'all_pmem' in conds else None
        ft = st.mean(conds['first_touch']) if 'first_touch' in conds else None
        vm = st.mean(conds['vmem_demote']) if 'vmem_demote' in conds else None
        if base and pm and pm > base:
            gap = pm - base; e['gap'] = round(100 * gap / base)
            if ft is not None: e['ft_cap'] = round(100 * (pm - ft) / gap)
            if vm is not None: e['vm_cap'] = round(100 * (pm - vm) / gap)
        fig.append(e)
    return fig


def footprints(path=FOOT_TSV):
    # Measured peak RSS (native, DRAM) per benchmark — the exact number the 25%
    # DRAM cap is derived from. bench \t kib \t mib. Shows the DRAM budget each
    # ladder actually ran under, so the caps are auditable, not assumed.
    out = []
    try:
        for line in open(path):
            p = line.rstrip('\n').split('\t')
            if len(p) >= 3 and p[2]:
                try:
                    mib = int(p[2])
                except ValueError:
                    continue
                gib = mib / 1024.0
                out.append({'key': p[0], 'name': P1_NAMES.get(p[0], p[0]),
                            'gib': round(gib, 2), 'mib': mib,
                            'dram25': round(gib * 0.25, 2),
                            'vpages': mib // 2, 'dram_vp': (mib // 2) * 25 // 100})
    except FileNotFoundError:
        return []
    out.sort(key=lambda e: e['gib'], reverse=True)
    return out


# Endpoint-overhead check: all-DRAM -> all-PMEM slowdown WITHOUT VMem (native
# numactl) vs WITH VMem (2MB substrate, tiering off). The pairs match -> VMem adds
# no measurable overhead to the endpoints, so the placement gap F1 recovers is real.
# Add a benchmark once both its native and VMem endpoints are measured.
GAP_COMPARE_RAW = [
    {'name': 'LULESH', 'native': {'dram': 2065.0, 'pmem': 4951.3},
     'vmem': {'dram': 2063.6, 'pmem': 4950.3}},   # vmem = mean of 3 repeats
]


def gap_compare():
    out = []
    for b in GAP_COMPARE_RAW:
        base = b['native']['dram']
        out.append({
            'name': b['name'],
            # VMem vs numactl overhead (%) for each endpoint — the point of this figure
            'dram_diff': round(100 * (b['vmem']['dram'] - b['native']['dram']) / b['native']['dram'], 2),
            'pmem_diff': round(100 * (b['vmem']['pmem'] - b['native']['pmem']) / b['native']['pmem'], 2),
            'bars': [
                {'label': 'all-DRAM · native', 'tier': 'hs3', 'dim': 0, 'x': round(b['native']['dram'] / base, 3), 'raw': b['native']['dram']},
                {'label': 'all-DRAM · VMem',   'tier': 'hs3', 'dim': 1, 'x': round(b['vmem']['dram'] / base, 3),   'raw': b['vmem']['dram']},
                {'label': 'all-PMEM · native', 'tier': 'hs2', 'dim': 0, 'x': round(b['native']['pmem'] / base, 3), 'raw': b['native']['pmem']},
                {'label': 'all-PMEM · VMem',   'tier': 'hs2', 'dim': 1, 'x': round(b['vmem']['pmem'] / base, 3),   'raw': b['vmem']['pmem']},
            ],
        })
    return out


def collect():
    d = {}
    d['hotset'] = HOTSET
    d['interval'] = INTERVAL
    d['compare'] = COMPARE
    d['gap_compare'] = gap_compare()
    d['phase1'] = p1_figures()
    d['footprint'] = footprints()
    d['migrate'] = {'demote': series('migrate', 'migrating region1 down'),
                    'promote': series('migrate', 'migrating region2 up')}
    d['replicate'] = {
        'to_pmem':   series('replicate', 'replicating region1 on pmem'),
        'to_dram':   series('replicate', 'replicating region2 on dram'),
        'flip_down': series('replicate', 'migrating region1 to pmem'),
        'flip_up':   series('replicate', 'migrating region2 to dram'),
    }
    # access bandwidth by tier, to show the migration actually moved the data
    d['access'] = {
        'dram': series('migrate', 'accessing region1 (post-fault)'),
        'pmem': series('migrate', 'accessing region2 (post-fault)'),
    }
    d['mlc1']  = mlc_copy('copy_matrix_1thread.txt')
    d['mlc16'] = mlc_copy('copy_matrix.txt')
    d['have']  = sorted(f[:-4] for f in os.listdir(RES) if f.endswith('.txt')) \
        if os.path.isdir(RES) else []
    return d


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VMem tiering — corsys4</title>
<style>
:root{color-scheme:light;--surface-0:#f6f6f4;--surface-1:#fcfcfb;--border:#e0dfda;
--text-primary:#0b0b0b;--text-secondary:#52514e;--text-muted:#78766f;
--s1:#2a78d6;--s2:#008300;--s3:#e87ba4;--s4:#eda100;--accent-bg:#eef4fd;--grid:#eceae5;
--hs1:#2a78d6;--hs2:#eb6834;--hs3:#1baf7a;--hs4:#eda100;--hs5:#e87ba4;--hs6:#008300}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
--surface-0:#111110;--surface-1:#1a1a19;--border:#33322f;--text-primary:#fff;
--text-secondary:#c3c2b7;--text-muted:#96948a;--s1:#3987e5;--s2:#008300;
--s3:#d55181;--s4:#c98500;--accent-bg:#16202e;--grid:#2a2a27;
--hs1:#3987e5;--hs2:#d95926;--hs3:#199e70;--hs4:#c98500;--hs5:#d55181;--hs6:#008300}}
:root[data-theme="dark"]{color-scheme:dark;--surface-0:#111110;--surface-1:#1a1a19;
--border:#33322f;--text-primary:#fff;--text-secondary:#c3c2b7;--text-muted:#96948a;
--s1:#3987e5;--s2:#008300;--s3:#d55181;--s4:#c98500;--accent-bg:#16202e;--grid:#2a2a27;
--hs1:#3987e5;--hs2:#d95926;--hs3:#199e70;--hs4:#c98500;--hs5:#d55181;--hs6:#008300}
*{box-sizing:border-box}
body{margin:0;background:var(--surface-0);color:var(--text-primary);
font:15px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:32px 20px 80px}
header{border-bottom:1px solid var(--border);padding-bottom:20px}
h1{font-size:25px;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:19px;margin:40px 0 4px}h3{font-size:15px;margin:22px 0 2px;font-weight:600}
.chartrow{display:flex;gap:4px;align-items:stretch}.chartrow>div:last-child{flex:1;min-width:0}
.ylab{writing-mode:vertical-rl;transform:rotate(180deg);text-align:center;font-size:11px;color:var(--text-muted);padding:4px 2px;white-space:nowrap}
.xlab{text-align:center;font-size:11px;color:var(--text-muted);margin-top:2px}
.gexpl{color:var(--text-muted);font-size:13px;margin:2px 0 8px;max-width:82ch}
.sub{color:var(--text-secondary);font-size:14px;margin:0}
.muted{color:var(--text-muted);font-size:13px}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;
padding:18px;margin-top:14px}
.row{display:grid;gap:14px;grid-template-columns:1fr 1fr}
@media(max-width:780px){.row{grid-template-columns:1fr}}
.tiles{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin-top:14px}
.tile{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:14px 16px}
.tile .v{font-size:23px;font-weight:650;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.tile .k{font-size:12px;color:var(--text-secondary);margin-top:2px}
.finding{background:var(--accent-bg);border:1px solid var(--border);
border-left:3px solid var(--s1);border-radius:8px;padding:14px 16px;margin-top:14px}
.finding p{margin:0;font-size:14px}
svg{display:block;width:100%;height:auto;overflow:visible}
text{font:11px ui-sans-serif,system-ui,sans-serif;fill:var(--text-secondary)}
text.lbl{fill:var(--text-primary);font-weight:600}
table{border-collapse:collapse;font-size:12.5px;margin-top:8px;width:100%}
th,td{border:1px solid var(--border);padding:4px 8px;text-align:right;
font-variant-numeric:tabular-nums}
th{background:var(--surface-0);font-weight:600;color:var(--text-secondary)}
td:first-child,th:first-child{text-align:left}
.warn{border-left-color:var(--s4)}
/* reviewer checklist (section 0) */
.qwrap{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:18px 20px;margin:18px 0 8px}
.qwrap>.qlead{font-size:13.5px;color:var(--text-secondary);margin:0 0 14px;max-width:90ch}
.qgrp{margin-top:16px}
.qgrp h3{font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:var(--text-secondary);margin:0 0 8px;font-weight:700}
.qitem{display:grid;grid-template-columns:34px 96px 1fr;gap:10px;align-items:start;padding:9px 0;border-top:1px solid var(--border)}
.qitem .qid{font-weight:700;font-size:13px;color:var(--text-muted);font-variant-numeric:tabular-nums}
.qbadge{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;padding:2px 7px;border-radius:20px;text-align:center;white-space:nowrap;border:1px solid transparent}
.qb-done{background:color-mix(in srgb,var(--hs3) 16%,transparent);color:var(--hs3);border-color:color-mix(in srgb,var(--hs3) 45%,transparent)}
.qb-partial{background:color-mix(in srgb,var(--hs4) 18%,transparent);color:var(--hs4);border-color:color-mix(in srgb,var(--hs4) 50%,transparent)}
.qb-active{background:color-mix(in srgb,var(--hs1) 16%,transparent);color:var(--hs1);border-color:color-mix(in srgb,var(--hs1) 45%,transparent)}
.qb-open{background:var(--surface-0);color:var(--text-muted);border-color:var(--border)}
.qb-blocked{background:color-mix(in srgb,var(--hs2) 16%,transparent);color:var(--hs2);border-color:color-mix(in srgb,var(--hs2) 45%,transparent)}
.qitem .qq{font-size:14px;font-weight:600;color:var(--text-primary);margin:0}
.qitem .qn{font-size:12.5px;color:var(--text-muted);margin:3px 0 0}
footer{margin-top:52px;padding-top:18px;border-top:1px solid var(--border);
font-size:13px;color:var(--text-muted)}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
.tip{position:fixed;pointer-events:none;opacity:0;transition:opacity .1s;
background:var(--surface-1);border:1px solid var(--border);border-radius:7px;
padding:7px 10px;font-size:12.5px;box-shadow:0 4px 14px rgba(0,0,0,.16);z-index:50;
font-variant-numeric:tabular-nums}
.legend{width:100%;font-size:12.5px;margin-top:8px}
.legend td{text-align:left;vertical-align:top}
.legend td:first-child{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;
white-space:nowrap;color:var(--text-primary)}
.lane{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;
padding:14px 16px;margin-top:12px;border-left:3px solid var(--s1)}
.lane.repl{border-left-color:var(--s2)}
.lane.promo{border-left-color:var(--s4)}
.lane h3{margin:2px 0 0}
.tag{font-size:11px;text-transform:uppercase;letter-spacing:.05em;font-weight:700}
.steps{display:flex;flex-wrap:wrap;align-items:center;gap:5px 6px;margin-top:10px}
.step{background:var(--surface-0);border:1px solid var(--border);border-radius:7px;
padding:5px 9px;font-size:12.5px;line-height:1.35}
.arrow{color:var(--text-muted);font-weight:600}
.knobline{margin-top:11px}
.chip{display:inline-block;background:var(--accent-bg);border:1px solid var(--border);
border-radius:6px;padding:1px 6px;margin:3px 4px 0 0;
font-family:ui-monospace,Menlo,monospace;font-size:11px}
</style></head><body><div class="wrap">
<header>
<h1>VMem tiering on corsys4</h1>
<p class="sub">DRAM + Optane, migration by <code>memcpy</code> (<code>VMEM_NO_DSA=1</code>) &mdash;
there is no DSA on this machine.</p>
<p class="muted" style="margin-top:6px">Xeon Gold 6246R, 16c/32t &middot; node 0 = 192 GB DRAM,
node 1 = 730 GB Optane (cpuless) &middot; 1 GiB regions, 2 MB pages &middot;
<b>mean of 3 passes</b>, spread shown throughout</p>
</header>

__REVIEW__

<div class="tiles" id="tiles"></div>

<h2>1. How the three paths operate</h2>
<p class="sub">Three paths move 2&nbsp;MB pages between the tiers. They share a small set of
containers, so work made by one is consumed by another &mdash; replication fills the eviction
ring that demotion drains, and promotion borrows that same ring to make room. All three are
<b>on by default</b>; disable one with its <code>*_INTERVAL_MS=0</code>.</p>

<div class="card">
  <h3>The shared containers</h3>
  <table class="legend"><tbody>
    <tr><td>free_dram / free_pmem</td><td>free-page pools, one per tier; the allocator draws DRAM from here first.</td></tr>
    <tr><td>active_dram / active_pmem</td><td>resident pages, one list per tier.</td></tr>
    <tr><td>eviction_ring</td><td>DRAM pages that already hold a PMEM replica &mdash; demotable with a pointer flip, no copy. Filled by replication; drained by demotion and by promotion&rsquo;s room-making.</td></tr>
    <tr><td>promotion_ring</td><td>hot PMEM pages the sweep has queued to copy up.</td></tr>
    <tr><td>vpte.replica</td><td>per page: pointer to a standby copy on the other tier (NULL if none). The invariant <code>replica&nbsp;&ne;&nbsp;NULL &rArr; source is write-protected</code> is what makes the flip safe.</td></tr>
    <tr><td>vpte.invalidation_count</td><td>writes seen to a replicated page; a write drops the stale replica and bumps this.</td></tr>
    <tr><td>vpte.dram_since</td><td>residency clock, stamped on every DRAM arrival; the grace window is measured against it.</td></tr>
  </tbody></table>
</div>

<div class="lane repl">
  <div class="tag" style="color:var(--s2)">Replication &mdash; prepay the copy</div>
  <h3>Background thread: copy a cold DRAM page down so it can later be demoted for free</h3>
  <div class="steps">
    <span class="step">every <b>REPL_INTERVAL_MS</b></span><span class="arrow">&rarr;</span>
    <span class="step">pick a cold DRAM page<br><span class="muted">not recently written, past its grace window</span></span><span class="arrow">&rarr;</span>
    <span class="step">copy DRAM&rarr;PMEM<br><span class="muted">takes a free_pmem page</span></span><span class="arrow">&rarr;</span>
    <span class="step">set <code>replica</code>, write-protect the source</span><span class="arrow">&rarr;</span>
    <span class="step">enqueue in <b>eviction_ring</b></span>
  </div>
  <div class="knobline">
    <span class="chip">REPL_INTERVAL_MS=200</span><span class="chip">REPL_MAX_PER_TICK=256</span>
    <span class="chip">REPL_INVAL_THRESH=4</span><span class="chip">REPL_MIN_AGE_MS=1000</span>
  </div>
</div>

<div class="lane demote">
  <div class="tag" style="color:var(--s1)">Demotion / eviction &mdash; flip the pointer</div>
  <h3>On demand: when the allocator needs DRAM and free_dram is empty</h3>
  <div class="steps">
    <span class="step">free_dram empty</span><span class="arrow">&rarr;</span>
    <span class="step">pop <b>eviction_ring</b></span><span class="arrow">&rarr;</span>
    <span class="step">flip mapping onto the PMEM replica<br><span class="muted">no copy &mdash; the replica already exists</span></span><span class="arrow">&rarr;</span>
    <span class="step">return the freed page to <b>free_dram</b></span>
  </div>
  <p class="muted" style="margin-top:9px">A write to a replicated page traps on the write-protect, drops the now-stale replica and bumps <code>invalidation_count</code> &mdash; so only clean pages are ever demoted for free.</p>
  <div class="knobline"><span class="chip">EVICT_COLD_THRESH=64 (profiler build only)</span></div>
</div>

<div class="lane promo">
  <div class="tag" style="color:var(--s4)">Promotion &mdash; speculative, mirrors replication</div>
  <h3>Background thread: copy a hot PMEM page up, evicting a cold one to make room</h3>
  <div class="steps">
    <span class="step">every <b>PROMO_INTERVAL_MS</b></span><span class="arrow">&rarr;</span>
    <span class="step">pick a hot PMEM page<br><span class="muted">by PROMO_HOT_METRIC</span></span><span class="arrow">&rarr;</span>
    <span class="step">queue in <b>promotion_ring</b></span><span class="arrow">&rarr;</span>
    <span class="step">make room: take free_dram,<br>else evict a cold replica-backed page</span><span class="arrow">&rarr;</span>
    <span class="step">copy PMEM&rarr;DRAM under write-protect</span><span class="arrow">&rarr;</span>
    <span class="step">flip mapping, free the PMEM source, stamp <code>dram_since</code></span>
  </div>
  <p class="muted" style="margin-top:9px">A concurrent write during the copy traps on the write-protect and lands on the new DRAM copy after the flip &mdash; the copy never tears.</p>
  <div class="knobline">
    <span class="chip">PROMO_INTERVAL_MS=200</span><span class="chip">PROMO_MAX_PER_TICK=64</span>
    <span class="chip">PROMO_HOT_METRIC=fifo</span><span class="chip">PROMO_HOT_THRESH=8</span>
  </div>
</div>

<div class="finding">
  <p><b>The metric is the open lever.</b> <code>fifo</code> is a policy-free control &mdash; it treats
  every PMEM page as equally hot, so with tiering on by default it churns (a recent run promoted
  2048 pages to serve a ~256-page hot set). <code>llc</code> and <code>write</code> need a profiler
  build; which one wins &mdash; and the best values for the intervals, batch sizes, and grace window
  &mdash; is what the knob sweep is for.</p>
</div>

<h2>2. Migration runs at the single-threaded memcpy limit</h2>
<p class="sub">VMem's own migration against what a bare <code>memcpy</code> achieves between the
same two tiers.</p>
<div class="finding">
  <p><b>There is no implementation inefficiency to find.</b> Migration hits 107&#37; of a
  single-threaded <code>memcpy</code> demoting and 92&#37; promoting. The bottleneck is that the
  copy is single-threaded &mdash; and the headroom from parallelising it is
  <b>wildly asymmetric</b>: ~1.7&times; for demotion, ~8.4&times; for promotion.</p>
</div>
<div class="card">
  <h3>Migration vs the memcpy baseline</h3>
  <p class="muted">baseline from <code>~/Projects/mlc</code>, same machine, same 1 GiB size
  &middot; <b>3 passes each</b></p>
  <div id="mig"></div>
  <div id="migTable"></div>
</div>
<div class="finding warn">
  <p><b>The comparison only means anything at matched thread counts.</b> Against the
  <i>16-thread</i> copy matrix VMem looks like it reaches 12&#37; of &ldquo;the hardware
  ceiling&rdquo; &mdash; a dramatic and completely wrong conclusion, since VMem's copy is
  single-threaded. Worth stating before someone else derives it.</p>
</div>

<h2>3. Replication turns migration into a pointer flip</h2>
<p class="sub">Replicate a region to the other tier first, then migrate it.</p>
<div class="finding">
  <p><b>Migration after replication is 156&ndash;235&times; faster</b>, because there is nothing
  left to copy &mdash; the mapping is flipped onto a replica that already exists. The copy cost
  does not vanish; it moves off the critical path into the background replication thread.</p>
</div>
<div class="card">
  <h3>Cost of the same 1 GiB move, with and without a replica</h3>
  <p class="muted"><b>3 passes each</b> &middot; log scale &mdash; the two regimes are ~2.5 decades
  apart</p>
  <div id="repl"></div>
  <div id="replTable"></div>
</div>
<div class="card">
  <h3>The honest trade</h3>
  <p class="muted">Replication does <b>not</b> reduce total work &mdash; it roughly triples it.
  A prior eviction run replicated all 1536 pages but only evicted 512, so ~3 GB of background
  copying bought ~257 ms off the latency path. Good when DRAM pressure is bursty and bandwidth is
  idle; bad on a machine already bandwidth-saturated.
  <code>VMEM_REPL_MAX_PER_TICK</code> and <code>VMEM_REPL_HOT_THRESH</code> govern exactly this,
  and <b>neither has been tuned</b>.</p>
</div>

<h2>4. Sanity: the data really moved</h2>
<div class="card">
  <h3>Single-threaded read bandwidth by tier</h3>
  <p class="muted">measured through VMem before migration &middot; <b>3 passes</b></p>
  <div id="acc"></div>
  <p class="muted" style="margin-top:10px">A ~3&times; gap, and every run reports
  <code>value matches</code> on both regions &mdash; so the pages changed tier and the contents
  survived. Post-migration the two swap, which is the check that the mapping flip is real rather
  than a no-op.</p>
</div>

<h2>5. Why any of this pays off: applications have a hot set</h2>
<p class="sub">Migration and replication only earn their cost if the pages worth keeping in DRAM are
few. Measured across six HPC and graph workloads &mdash; hardware LLC-miss sampling, tiering off,
every page resident in DRAM so the profile is the application&rsquo;s own, not the policy&rsquo;s.</p>
<div class="finding">
  <p><b>80&#37; of last-level-cache misses fall in just 0.9&ndash;5.5&#37; of an application&rsquo;s
  resident memory.</b> The hot set is tiny &mdash; exactly the regime where promoting a few pages
  beats the <code>fifo</code> churn from section&nbsp;1 (2048 pages moved to serve a ~256-page hot
  set). <b>BFS is the exception that proves the rule:</b> its misses spread out &mdash; no decile
  below ~10&#37; &mdash; so it has no hot set to promote, a workload tiering should leave alone.</p>
</div>
<div class="card">
  <h3>Cumulative miss coverage vs. hot-set size</h3>
  <p class="muted">the hottest pages&rsquo; share of misses (y) against their share of resident
  footprint (x, log) &middot; markers are measured deciles &middot; <code>sample_period&nbsp;10000</code>,
  2&nbsp;MB pages, tiering off</p>
  <div id="conc"></div>
  <div id="concLegend"></div>
  <p class="muted" style="margin-top:11px">Read it as: the hottest <i>X</i>&#37; of memory captures
  <i>Y</i>&#37; of misses. A steep left edge is a sharp hot set; BFS (dashed) rises gradually and
  never concentrates. Curves begin at the 50&#37; decile &mdash; the finest coverage the profiler
  reports &mdash; so they show the top of each distribution.</p>
  <div id="concTable"></div>
</div>
<div class="finding">
  <p><b>One profiler setting resolves every hot set: <code>sample_period&nbsp;10000</code>.</b> A
  24-run sweep of the sampling rate showed the miss-rich workloads saturate far coarser and the
  miss-sparse ones (AMG, LULESH) converge exactly here; sampling denser only drops ring-buffer
  samples on the miss-rich workloads with no change to the answer. So the hot set can be found
  cheaply, with a single global rate rather than per-application tuning.</p>
</div>

<h2>6. Locking the profiler interval: longer windows, stronger signal</h2>
<p class="sub">The sample rate is locked; the other profiler knob is the analysis window. It has no
effect on the <i>cumulative</i> hot set above &mdash; but the <b>live</b> policy decides from
<i>per-window</i> counts, and a window must gather enough misses on a page to tell hot from cold.
Same setup: tiering off, all DRAM, <code>sample_period&nbsp;10000</code>; only the window varies.</p>
<div class="finding">
  <p><b>Longer windows give a stronger, steadier signal &mdash; for the workloads that have a hot
  set to begin with.</b> For the miss-rich workloads the hottest page&rsquo;s per-window miss count
  climbs past a usable threshold by ~500&nbsp;ms and keeps rising, and the per-window hot set holds
  steady. <b>The miss-sparse workloads never get there:</b> AMG, LULESH and BFS see only 2&ndash;6
  misses on their hottest page at <i>any</i> window &mdash; too few to threshold, and too noisy to
  trust. A per-window policy simply cannot resolve them at this sample rate.</p>
</div>
<div class="card">
  <h3>Per-window hottest-page miss count vs. window length</h3>
  <p class="muted">median over all windows in a run &middot; both axes log &middot; the dashed line
  is roughly the count a hot/cold threshold must sit above to discriminate</p>
  <div id="intv"></div>
  <div id="intvLegend"></div>
  <p class="muted" style="margin-top:11px">Read it as: how strong is the per-window hotness signal
  the policy sees? Miss-rich workloads (solid) cross into thresholdable territory around
  500&nbsp;ms; miss-sparse workloads (dashed) stay pinned near the noise floor no matter how long
  the window. <b>Locked interval: 1000&nbsp;ms</b> &mdash; strong, stable per-window signal for
  every workload that has one, still one decision per second.</p>
</div>

<h2>7. A second signal: sampling accesses, not just misses</h2>
<p class="sub">The low-miss-rate workloads (AMG, LULESH, BFS) can&rsquo;t be resolved by miss sampling at
any window &mdash; their misses are hidden by the prefetcher. But those pages are still
<i>accessed</i>. So we also sample <code>MEM_INST_RETIRED.ALL_LOADS</code> &mdash; every retired
load, hit or miss &mdash; and attribute it to vpages the same way. Same window sweep, tiering off.</p>
<div class="finding">
  <p><b>The access signal is the stronger, more universal one.</b> It clears the thresholdable line
  for <i>all six</i> workloads where the miss signal clears it for only three &mdash; and it rescues
  the exact three that miss sampling gives up on (AMG&rsquo;s hottest page: <b>2 misses vs 849
  accesses</b> per window). Where both work, they track each other. <b>The miss signal keeps two
  jobs:</b> it flags pages whose tier placement actually <i>matters</i> (a cache-resident hot page
  doesn&rsquo;t need DRAM), and on churny workloads like Graph500 it reads <i>steadier</i> than the
  access signal, which faithfully &mdash; and noisily &mdash; tracks the moving frontier.</p>
</div>
<div class="card">
  <h3>Per-window hottest-page count: miss signal vs. access signal</h3>
  <p class="muted">one panel per workload &middot; both axes log &middot; dashed line = roughly the
  count a hot/cold threshold must sit above &middot; <code>sample_period</code> 1e4 (miss) / 1e5 (access)</p>
  <div style="display:flex;gap:20px;margin:6px 0 4px 2px;font-size:12.5px">
    <span style="display:inline-flex;align-items:center;gap:6px"><span style="width:14px;height:2px;background:var(--hs1)"></span>LLC misses</span>
    <span style="display:inline-flex;align-items:center;gap:6px"><span style="width:14px;height:2px;background:var(--hs2)"></span>accesses (ALL_LOADS)</span>
  </div>
  <div id="cmp" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px 16px;margin-top:6px"></div>
  <p class="muted" style="margin-top:12px">Top row (miss-rich): both signals rise together. Bottom
  row (miss-sparse): the miss line stays pinned at the noise floor while the access line climbs into
  usable range &mdash; often at far shorter windows. <b>Open question:</b> whether access-driven
  placement actually improves runtime, or over-promotes cache-resident pages, needs a tiering-on test.</p>
</div>

<div>
<h2>8. VMem tiering vs the DRAM&ndash;PMEM placement gap</h2>
<p class="muted">Auto-generated from the Phase-1 <code>results.tsv</code> &mdash; they extend as
benchmarks land. Every tiering run is on the VMem 2&nbsp;MB substrate at exactly 25% DRAM.</p>

<h3>Memory footprint &mdash; measured peak RSS &amp; the 25% DRAM budget</h3>
<p class="gexpl">Each benchmark's <b>peak resident set size</b>, measured from a real native run (<code>/usr/bin/time&nbsp;-v</code>,
DRAM node) &mdash; the exact number every 25% DRAM cap is derived from, so the caps are auditable, not estimated. The
faded segment is the <b>25% DRAM budget</b> the constrained runs are pinned to; the rest must live on PMEM.</p>
<div class="chartrow"><div class="ylab">peak RSS (GiB)</div>
  <div><div id="ffoot"></div><div class="xlab">benchmark</div></div></div>

<h3>Placement ladder &mdash; tiering recovers the gap</h3>
<p class="gexpl">Per benchmark, execution time in four placements, each normalized to that benchmark's all-DRAM
so different metrics (grind, wall-clock, avg-time) are comparable. The distance from <b>all-DRAM</b> to
<b>all-PMEM</b> is the placement gap; <b>first-touch</b> is naive DRAM-first, <b>VMem&nbsp;demote</b> is tuned
demotion. Error bars = 95% CI.</p>
<div class="legend" id="legF1" style="display:flex;flex-wrap:wrap;gap:10px 18px;margin:2px 0 8px;font-size:12.5px"></div>
<div class="chartrow"><div class="ylab">execution time (× vs all-DRAM, lower is better)</div>
  <div><div id="f1"></div><div class="xlab">benchmark</div></div></div>

<h3>Gap capture &mdash; how much each approach recovers</h3>
<p class="gexpl">Of the full all-PMEM&harr;all-DRAM gap, the share each approach claws back &mdash; higher is
better. VMem demotion recovering far more than first-touch is the headline. Benchmarks with a measured all-PMEM only.</p>
<div class="legend" style="display:flex;gap:16px;margin:2px 0 6px;font-size:12.5px">
  <span style="display:inline-flex;align-items:center;gap:6px"><span style="width:11px;height:11px;border-radius:3px;background:var(--hs4)"></span>first-touch</span>
  <span style="display:inline-flex;align-items:center;gap:6px"><span style="width:11px;height:11px;border-radius:3px;background:var(--hs1)"></span>VMem demote</span></div>
<div class="chartrow"><div class="ylab">% of the DRAM&harr;PMEM gap recovered</div>
  <div><div id="f8"></div><div class="xlab">benchmark</div></div></div>
<p class="muted" id="p1prov" style="margin-top:10px"></p>

<h3>VMem overhead &mdash; VMem vs numactl at the endpoints</h3>
<p class="gexpl">Not DRAM vs PMEM &mdash; this is <b>VMem vs numactl</b>: the same all-DRAM and all-PMEM runs done
<b>with</b> VMem (2&nbsp;MB substrate, tiering off) vs plain <code>numactl</code>. Each native/VMem pair sitting
on top of the other (&lt;0.1%, delta printed under each benchmark) shows routing memory through VMem is free.</p>
<div class="legend" style="display:flex;flex-wrap:wrap;gap:10px 18px;margin:2px 0 8px;font-size:12.5px">
  <span style="display:inline-flex;align-items:center;gap:6px"><span style="width:11px;height:11px;border-radius:3px;background:var(--hs3)"></span>all-DRAM</span>
  <span style="display:inline-flex;align-items:center;gap:6px"><span style="width:11px;height:11px;border-radius:3px;background:var(--hs2)"></span>all-PMEM</span>
  <span class="muted">solid = without VMem (numactl) &middot; faded = with VMem</span></div>
<div class="chartrow"><div class="ylab">× vs native all-DRAM</div>
  <div><div id="fgap"></div><div class="xlab">benchmark</div></div></div>
</div>

<div class="finding warn" style="margin-top:34px">
  <p><b>Not yet captured.</b> Two of the four microbenchmark groups are missing from this page:
  <b>eviction</b> (background replication under forced DRAM pressure) and <b>promotion</b>
  (speculative replication, evicting cold pages to make room). Both are now verified by the
  regression suite (<code>run_suite.sh</code>); their <i>throughput</i> is what is missing here. Earlier, on 2026-07-19 &mdash;
  eviction flipped exactly 512 of 1536 pages, the precise overflow; promotion armed/confirmed/
  completed 256/256/256 for a 3.1&times; read speedup &mdash; but those runs went to stdout and were
  never saved. The capture script now exists; the run died entering group C.</p>
</div>

<footer>
Generated by <code>bench/viz/build.py</code> from <code>bench/results/</code> and
<code>~/Projects/mlc/results/</code>. Regenerate with <code>python3 bench/viz/build.py</code>.
<br>files present: <span id="have"></span>
<br>build <code>__BUILDID__</code>
</footer>
</div><div class="tip" id="tip"></div>
<script>
const D = __DATA__;
const tip=document.getElementById('tip');
const fmt=(n,d=2)=>Number(n).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d});
function showTip(e,h){tip.innerHTML=h;tip.style.opacity=1;const r=tip.getBoundingClientRect();
let x=e.clientX+14,y=e.clientY-10;if(x+r.width>innerWidth-8)x=e.clientX-r.width-14;
tip.style.left=x+'px';tip.style.top=Math.max(8,y)+'px';}
function hideTip(){tip.style.opacity=0;}
const SVG='http://www.w3.org/2000/svg';
const el=(n,a={})=>{const e=document.createElementNS(SVG,n);for(const k in a)e.setAttribute(k,a[k]);return e;};
const svg=(w,h)=>el('svg',{viewBox:`0 0 ${w} ${h}`,preserveAspectRatio:'xMidYMid meet'});

/* horizontal bars; log:true when the values span decades */
function bars(host,rows,unit,opts={}){
  const W=560,rowH=opts.rowH||36,pad={l:opts.l||150,r:86,t:8,b:26};
  const H=pad.t+rows.length*rowH+pad.b;const s=svg(W,H);
  const vals=rows.map(r=>r.v),log=!!opts.log;
  const lo=log?Math.min(...vals)*0.6:0,hi=Math.max(...vals)*(log?1.8:1.12);
  const x=v=>log
    ? pad.l+(Math.log10(v)-Math.log10(lo))/(Math.log10(hi)-Math.log10(lo))*(W-pad.l-pad.r)
    : pad.l+(v-lo)/(hi-lo)*(W-pad.l-pad.r);
  rows.forEach((r,i)=>{
    const y=pad.t+i*rowH+4,h=rowH-13,g=el('g');
    g.appendChild(el('rect',{x:pad.l,y,width:Math.max(2,x(r.v)-pad.l),height:h,rx:4,
      fill:r.color||'var(--s1)',opacity:r.dim?0.45:1}));
    const lb=el('text',{x:pad.l-10,y:y+h/2+4,'text-anchor':'end',class:'lbl'});
    lb.textContent=r.label;g.appendChild(lb);
    const vt=el('text',{x:x(r.v)+8,y:y+h/2+4,class:'lbl'});
    vt.textContent=fmt(r.v,r.v>=100?0:2);g.appendChild(vt);
    if(r.tip){g.addEventListener('mousemove',e=>showTip(e,r.tip));
      g.addEventListener('mouseleave',hideTip);}
    s.appendChild(g);
  });
  const ax=el('text',{x:pad.l,y:H-8});
  ax.textContent=unit+(log?' — log scale':'');s.appendChild(ax);
  document.getElementById(host).appendChild(s);
}
const sp=o=>o?`spread ${fmt(o.spread,3)} over ${o.n} passes`:'';

/* miss-concentration curves: cumulative % of misses (y) vs % of footprint (x, log) */
function conc(host,data){
  const W=620,H=336,pad={l:42,r:14,t:12,b:38};
  const x0=pad.l,x1=W-pad.r,y0=H-pad.b,y1=pad.t;
  const LXMIN=Math.log10(0.4),LXMAX=Math.log10(100),YMIN=45,YMAX=100;
  const px=v=>x0+(Math.log10(v)-LXMIN)/(LXMAX-LXMIN)*(x1-x0);
  const py=v=>y0+(v-YMIN)/(YMAX-YMIN)*(y1-y0);
  const s=svg(W,H);
  [50,60,70,80,90,100].forEach(t=>{
    s.appendChild(el('line',{x1:x0,x2:x1,y1:py(t),y2:py(t),stroke:'var(--grid)'}));
    const tx=el('text',{x:x0-7,y:py(t)+4,'text-anchor':'end'});tx.textContent=t;s.appendChild(tx);});
  [0.5,1,2,5,10,20,50,100].forEach(t=>{
    s.appendChild(el('line',{x1:px(t),x2:px(t),y1:y0,y2:y1,stroke:'var(--grid)'}));
    const tx=el('text',{x:px(t),y:y0+16,'text-anchor':'middle'});tx.textContent=t;s.appendChild(tx);});
  s.appendChild(el('line',{x1:x0,x2:x1,y1:y0,y2:y0,stroke:'var(--border)'}));
  const xl=el('text',{x:(x0+x1)/2,y:H-3,'text-anchor':'middle',class:'lbl'});
  xl.textContent='hot-set size — % of footprint (log)';s.appendChild(xl);
  const yl=el('text',{x:11,y:(y0+y1)/2,'text-anchor':'middle',class:'lbl',
    transform:`rotate(-90 11 ${(y0+y1)/2})`});yl.textContent='% of LLC misses';s.appendChild(yl);
  data.series.forEach(se=>{
    const d=se.pts.map((p,i)=>(i?'L':'M')+px(p[0]).toFixed(1)+' '+py(p[1]).toFixed(1)).join(' ');
    const path=el('path',{d,fill:'none','stroke-width':2,'stroke-linejoin':'round','stroke-linecap':'round'});
    path.style.stroke=`var(--${se.c})`;
    if(se.diffuse)path.setAttribute('stroke-dasharray','2 4');
    s.appendChild(path);});
  data.series.forEach(se=>se.pts.forEach(p=>{
    const c=el('circle',{cx:px(p[0]),cy:py(p[1]),r:3.5,stroke:'var(--surface-1)','stroke-width':1.5});
    c.style.fill=`var(--${se.c})`;c.style.cursor='pointer';
    c.addEventListener('mousemove',e=>showTip(e,
      `<b style="color:var(--${se.c})">${se.nm}</b><br>${p[1]}% of misses<br>in top ${p[0]}% of footprint`));
    c.addEventListener('mouseleave',hideTip);
    s.appendChild(c);}));
  document.getElementById(host).appendChild(s);
  // legend / summary strip (divs, not a table, to dodge the global td border),
  // sorted by hot-set size; doubles as the labeled legend + light-mode relief
  const mx=Math.max(...data.series.map(z=>z.hot));
  const rows=data.series.slice().sort((a,b)=>a.hot-b.hot).map(se=>
    `<div style="display:grid;grid-template-columns:12px minmax(84px,auto) 1fr 46px;`+
    `align-items:center;gap:9px;padding:3px 0;font-size:12.5px">`+
    `<span style="width:10px;height:10px;border-radius:2px;background:var(--${se.c})"></span>`+
    `<span style="white-space:nowrap;font-weight:600">${se.nm}`+
    `${se.diffuse?' <span class="muted" style="font-weight:400">· diffuse</span>':''}</span>`+
    `<span style="height:6px;border-radius:3px;background:var(--${se.c});opacity:.85;`+
    `width:${(se.hot/mx*100).toFixed(0)}%"></span>`+
    `<span style="text-align:right;font-variant-numeric:tabular-nums;color:var(--text-secondary)">`+
    `${se.hot.toFixed(1)}%</span></div>`).join('');
  document.getElementById(host+'Legend').innerHTML=
    `<p class="muted" style="margin:12px 0 4px">hot set = share of footprint holding 80% of misses</p>`+
    `<div style="max-width:420px">${rows}</div>`;
}

/* signal strength vs window length: log-log lines + a threshold reference line */
function intv(host,data){
  const W=620,H=340,pad={l:44,r:14,t:12,b:40};
  const x0=pad.l,x1=W-pad.r,y0=H-pad.b,y1=pad.t;
  const xs=data.ms, LXMIN=Math.log10(20),LXMAX=Math.log10(3200);
  const LYMIN=Math.log10(1.5),LYMAX=Math.log10(220);
  const px=v=>x0+(Math.log10(v)-LXMIN)/(LXMAX-LXMIN)*(x1-x0);
  const py=v=>y0+(Math.log10(v)-LYMIN)/(LYMAX-LYMIN)*(y1-y0);
  const s=svg(W,H);
  [2,5,10,20,50,100,200].forEach(t=>{
    s.appendChild(el('line',{x1:x0,x2:x1,y1:py(t),y2:py(t),stroke:'var(--grid)'}));
    const tx=el('text',{x:x0-7,y:py(t)+4,'text-anchor':'end'});tx.textContent=t;s.appendChild(tx);});
  xs.forEach(t=>{
    s.appendChild(el('line',{x1:px(t),x2:px(t),y1:y0,y2:y1,stroke:'var(--grid)'}));
    const tx=el('text',{x:px(t),y:y0+16,'text-anchor':'middle'});tx.textContent=t;s.appendChild(tx);});
  // threshold reference line
  s.appendChild(el('line',{x1:x0,x2:x1,y1:py(data.thresh),y2:py(data.thresh),
    stroke:'var(--text-muted)','stroke-width':1.5,'stroke-dasharray':'5 4'}));
  const rl=el('text',{x:x1-2,y:py(data.thresh)-5,'text-anchor':'end',class:'lbl'});
  rl.textContent='thresholdable';s.appendChild(rl);
  const xl=el('text',{x:(x0+x1)/2,y:H-3,'text-anchor':'middle',class:'lbl'});
  xl.textContent='analysis window (ms, log)';s.appendChild(xl);
  const yl=el('text',{x:11,y:(y0+y1)/2,'text-anchor':'middle',class:'lbl',
    transform:`rotate(-90 11 ${(y0+y1)/2})`});
  yl.textContent='hottest-page misses / window';s.appendChild(yl);
  data.series.forEach(se=>{
    const pts=se.sig.map((v,i)=>v==null?null:[xs[i],v]).filter(Boolean);
    const d=pts.map((p,i)=>(i?'L':'M')+px(p[0]).toFixed(1)+' '+py(p[1]).toFixed(1)).join(' ');
    const path=el('path',{d,fill:'none','stroke-width':2,'stroke-linejoin':'round','stroke-linecap':'round'});
    path.style.stroke=`var(--${se.c})`;
    if(se.cls=='sparse')path.setAttribute('stroke-dasharray','2 4');
    s.appendChild(path);
    pts.forEach(p=>{
      const c=el('circle',{cx:px(p[0]),cy:py(p[1]),r:3.5,stroke:'var(--surface-1)','stroke-width':1.5});
      c.style.fill=`var(--${se.c})`;c.style.cursor='pointer';
      c.addEventListener('mousemove',e=>showTip(e,
        `<b style="color:var(--${se.c})">${se.nm}</b><br>${p[1]} misses on hottest page<br>per ${p[0]} ms window`));
      c.addEventListener('mouseleave',hideTip);
      s.appendChild(c);});
  });
  document.getElementById(host).appendChild(s);
  const rich=data.series.filter(z=>z.cls=='rich'),sparse=data.series.filter(z=>z.cls=='sparse');
  const chip=se=>`<span style="display:inline-flex;align-items:center;gap:6px;margin-right:16px;font-size:12.5px">`+
    `<span style="width:14px;height:2px;background:var(--${se.c});${se.cls=='sparse'?'opacity:.6':''}"></span>${se.nm}</span>`;
  document.getElementById(host+'Legend').innerHTML=
    `<div style="margin-top:12px"><span class="muted" style="font-size:12px">miss-rich (has a hot set):&nbsp;</span>`+
    rich.map(chip).join('')+`</div>`+
    `<div style="margin-top:4px"><span class="muted" style="font-size:12px">miss-sparse (no usable per-window signal):&nbsp;</span>`+
    sparse.map(chip).join('')+`</div>`;
}

/* small multiples: one mini log-log chart per benchmark, miss vs access */
function cmp(host,data){
  const box=document.getElementById(host);
  const W=250,H=158,pad={l:26,r:8,t:6,b:20};
  const x0=pad.l,x1=W-pad.r,y0=H-pad.b,y1=pad.t;
  const LXMIN=Math.log10(20),LXMAX=Math.log10(3200),LYMIN=0,LYMAX=Math.log10(1000);
  const px=v=>x0+(Math.log10(v)-LXMIN)/(LXMAX-LXMIN)*(x1-x0);
  const py=v=>y0+(Math.log10(Math.max(v,1))-LYMIN)/(LYMAX-LYMIN)*(y1-y0);
  const xs=data.windows;
  data.benches.forEach(bn=>{
    const cell=document.createElement('div');
    cell.innerHTML='<div style="font-size:12.5px;font-weight:600;margin:0 0 1px 3px">'+bn.nm+'</div>';
    const s=svg(W,H);
    [1,10,100,1000].forEach(t=>{
      s.appendChild(el('line',{x1:x0,x2:x1,y1:py(t),y2:py(t),stroke:'var(--grid)'}));
      const tx=el('text',{x:x0-4,y:py(t)+3,'text-anchor':'end',style:'font-size:9px'});tx.textContent=t;s.appendChild(tx);});
    [25,250,2500].forEach(t=>{const tx=el('text',{x:px(t),y:y0+12,'text-anchor':'middle',style:'font-size:9px'});tx.textContent=t;s.appendChild(tx);});
    s.appendChild(el('line',{x1:x0,x2:x1,y1:py(data.thresh),y2:py(data.thresh),
      stroke:'var(--text-muted)','stroke-width':1,'stroke-dasharray':'4 3'}));
    [['miss','--hs1',bn.miss],['access','--hs2',bn.access]].forEach(function(sig){
      const nm=sig[0],col=sig[1],vals=sig[2];
      const pts=vals.map((v,i)=>v==null?null:[xs[i],v]).filter(Boolean);
      const d=pts.map((p,i)=>(i?'L':'M')+px(p[0]).toFixed(1)+' '+py(p[1]).toFixed(1)).join(' ');
      const path=el('path',{d,fill:'none','stroke-width':1.8,'stroke-linejoin':'round','stroke-linecap':'round'});
      path.style.stroke='var('+col+')';s.appendChild(path);
      pts.forEach(p=>{
        const c=el('circle',{cx:px(p[0]),cy:py(p[1]),r:2.4,stroke:'var(--surface-1)','stroke-width':1});
        c.style.fill='var('+col+')';c.style.cursor='pointer';
        c.addEventListener('mousemove',e=>showTip(e,'<b style="color:var('+col+')">'+bn.nm+' · '+nm+
          '</b><br>'+p[1]+' on hottest page<br>per '+p[0]+' ms window'));
        c.addEventListener('mouseleave',hideTip);s.appendChild(c);});
    });
    cell.appendChild(s);box.appendChild(cell);
  });
}

function build(){
  const M=D.migrate,R=D.replicate,A=D.access,m1=D.mlc1,m16=D.mlc16;
  document.getElementById('tiles').innerHTML=[
    [fmt(M.demote.mean)+' GB/s','migration, demote'],
    [fmt(M.promote.mean)+' GB/s','migration, promote'],
    [Math.round(R.flip_down.mean/M.demote.mean)+'×','faster with a replica'],
    [fmt(M.demote.mean/m1.demote*100,0)+'%','of 1-thread memcpy'],
  ].map(r=>`<div class="tile"><div class="v">${r[0]}</div><div class="k">${r[1]}</div></div>`).join('');
  document.getElementById('have').textContent=D.have.join(', ')||'none';

  bars('mig',[
    {label:'VMem demote',v:M.demote.mean,color:'var(--s1)',
     tip:`<b>VMem demote</b><br>${fmt(M.demote.mean)} GB/s<br>${sp(M.demote)}`},
    {label:'memcpy 1 thread',v:m1.demote,color:'var(--s1)',dim:1,
     tip:`<b>memcpy, 1 thread</b><br>${fmt(m1.demote)} GB/s<br>the fair baseline`},
    {label:'memcpy 16 threads',v:m16.demote,color:'var(--s1)',dim:1,
     tip:`<b>memcpy, 16 threads</b><br>${fmt(m16.demote)} GB/s<br>not comparable — VMem is single-threaded`},
    {label:'VMem promote',v:M.promote.mean,color:'var(--s2)',
     tip:`<b>VMem promote</b><br>${fmt(M.promote.mean)} GB/s<br>${sp(M.promote)}`},
    {label:'memcpy 1 thread',v:m1.promote,color:'var(--s2)',dim:1,
     tip:`<b>memcpy, 1 thread</b><br>${fmt(m1.promote)} GB/s`},
    {label:'memcpy 16 threads',v:m16.promote,color:'var(--s2)',dim:1,
     tip:`<b>memcpy, 16 threads</b><br>${fmt(m16.promote)} GB/s`},
  ],'GB/s');
  document.getElementById('migTable').innerHTML=
   `<table><tr><th>direction</th><th>VMem</th><th>memcpy 1t</th><th>at</th>
     <th>memcpy 16t</th><th>headroom</th></tr>
    <tr><td>demote DRAM→PMEM</td><td>${fmt(M.demote.mean)}</td><td>${fmt(m1.demote)}</td>
      <td><b>${fmt(M.demote.mean/m1.demote*100,0)}%</b></td><td>${fmt(m16.demote)}</td>
      <td>${fmt(m16.demote/M.demote.mean,1)}×</td></tr>
    <tr><td>promote PMEM→DRAM</td><td>${fmt(M.promote.mean)}</td><td>${fmt(m1.promote)}</td>
      <td><b>${fmt(M.promote.mean/m1.promote*100,0)}%</b></td><td>${fmt(m16.promote)}</td>
      <td>${fmt(m16.promote/M.promote.mean,1)}×</td></tr></table>`;

  bars('repl',[
    {label:'copy, no replica ↓',v:M.demote.mean,color:'var(--s1)',
     tip:`<b>demote, real copy</b><br>${fmt(M.demote.mean)} GB/s<br>${sp(M.demote)}`},
    {label:'flip onto replica ↓',v:R.flip_down.mean,color:'var(--s2)',
     tip:`<b>demote, replica exists</b><br>${fmt(R.flip_down.mean,0)} GB/s<br>${sp(R.flip_down)}<br>no copy — mapping flip`},
    {label:'copy, no replica ↑',v:M.promote.mean,color:'var(--s1)',
     tip:`<b>promote, real copy</b><br>${fmt(M.promote.mean)} GB/s<br>${sp(M.promote)}`},
    {label:'flip onto replica ↑',v:R.flip_up.mean,color:'var(--s2)',
     tip:`<b>promote, replica exists</b><br>${fmt(R.flip_up.mean,0)} GB/s<br>${sp(R.flip_up)}`},
  ],'GB/s',{log:true});
  document.getElementById('replTable').innerHTML=
   `<table><tr><th></th><th>replicate (the copy)</th><th>then migrate</th><th>speedup</th></tr>
    <tr><td>DRAM→PMEM</td><td>${fmt(R.to_pmem.mean)}</td><td>${fmt(R.flip_down.mean,0)}</td>
      <td><b>${Math.round(R.flip_down.mean/M.demote.mean)}×</b></td></tr>
    <tr><td>PMEM→DRAM</td><td>${fmt(R.to_dram.mean)}</td><td>${fmt(R.flip_up.mean,0)}</td>
      <td><b>${Math.round(R.flip_up.mean/M.promote.mean)}×</b></td></tr></table>
    <p class="muted" style="margin-top:8px">Replication costs the same as migration
    (${fmt(R.to_pmem.mean)} vs ${fmt(M.demote.mean)}) — it <i>is</i> the same memcpy. What changes
    is <i>when</i> you pay it.</p>`;

  bars('acc',[
    {label:'DRAM',v:A.dram.mean,color:'var(--s1)',tip:`<b>DRAM</b><br>${fmt(A.dram.mean)} GB/s<br>${sp(A.dram)}`},
    {label:'Optane',v:A.pmem.mean,color:'var(--s3)',tip:`<b>Optane</b><br>${fmt(A.pmem.mean)} GB/s<br>${sp(A.pmem)}`},
  ],'GB/s');

  const HS=D.hotset;
  conc('conc',HS);
  const th='<tr><th>workload</th>'+HS.cov.map(c=>`<th>${c}%</th>`).join('')+'</tr>';
  const rs=HS.series.map(se=>`<tr><td>${se.nm}${se.diffuse?' <span class="muted">(diffuse)</span>':''}</td>`+
    se.pts.map(p=>`<td>${p[0].toFixed(1)}</td>`).join('')+'</tr>').join('');
  document.getElementById('concTable').innerHTML=
    `<p class="muted" style="margin:14px 0 2px">hot-set size (% of resident footprint) at each miss-coverage decile</p>`+
    `<table>${th}${rs}</table>`;

  intv('intv',D.interval);
  cmp('cmp',D.compare);

  drawFoot();drawGap();drawF1();drawF8();
}

// Measured peak RSS per bench: total bar (GiB) split into the 25% DRAM budget
// (bottom, DRAM color) and the PMEM spill (top). The exact caps, made auditable.
function drawFoot(){
  const F=D.footprint||[]; const host=document.getElementById('ffoot'); if(!host){return;}
  if(!F.length){host.innerHTML='<p class="muted">No footprints measured yet (run <code>MEASURE=1 ./phase1.sh</code>).</p>';return;}
  const W=920,mL=46,mR=14,mT=14,mB=52,gGap=Math.min(70,600/F.length);
  const maxV=Math.max(...F.map(b=>b.gib))*1.12;
  const H=280,pW=W-mL-mR,pH=H-mT-mB,gW=(pW-gGap*F.length)/F.length;
  const s=svg(W,H),Y=v=>mT+pH*(1-v/maxV);
  const step=maxV>16?4:maxV>8?2:1;
  for(let g=0;g<=maxV;g+=step){
    s.appendChild(el('line',{x1:mL,x2:mL+pW,y1:Y(g),y2:Y(g),stroke:'var(--grid)'}));
    const t=el('text',{x:mL-6,y:Y(g)+3,'text-anchor':'end',fill:'var(--text-muted)','font-size':11});t.textContent=g;s.appendChild(t);}
  F.forEach((b,bi)=>{
    const bw=Math.min(90,gW),gx=mL+gGap/2+bi*(gW+gGap)+(gW-bw)/2;
    const hT=pH*(b.gib/maxV),hD=pH*(b.dram25/maxV);
    // PMEM spill (top, 75%)
    const rp=el('rect',{x:gx,y:mT+pH-hT,width:bw,height:Math.max(2,hT-hD),rx:3,fill:'var(--hs2)',opacity:.85,style:'cursor:pointer'});
    rp.addEventListener('mousemove',e=>showTip(e,`<b>${b.name} &middot; PMEM spill</b><br>${fmt(b.gib-b.dram25)} GiB (75%)`));
    rp.addEventListener('mouseleave',hideTip);s.appendChild(rp);
    // DRAM budget (bottom, 25%)
    const rd=el('rect',{x:gx,y:mT+pH-hD,width:bw,height:Math.max(2,hD),rx:3,fill:'var(--hs3)',style:'cursor:pointer'});
    rd.addEventListener('mousemove',e=>showTip(e,`<b>${b.name} &middot; DRAM budget</b><br>${fmt(b.dram25)} GiB (25% cap)<br>${b.dram_vp} vpages`));
    rd.addEventListener('mouseleave',hideTip);s.appendChild(rd);
    // total label
    const tv=el('text',{x:gx+bw/2,y:Y(b.gib)-5,'text-anchor':'middle',fill:'var(--text-primary)','font-size':12,style:'font-weight:600'});tv.textContent=fmt(b.gib)+' GiB';s.appendChild(tv);
    const nm=el('text',{x:gx+bw/2,y:H-32,'text-anchor':'middle',fill:'var(--text-primary)','font-size':13,style:'font-weight:600'});nm.textContent=b.name;s.appendChild(nm);
    const sub=el('text',{x:gx+bw/2,y:H-16,'text-anchor':'middle',fill:'var(--text-muted)','font-size':11});sub.textContent=`25%: ${fmt(b.dram25)} GiB`;s.appendChild(sub);
  });
  const lg=document.createElement('div');lg.style.cssText='display:flex;gap:16px;margin:8px 0 0;font-size:12.5px';
  lg.innerHTML=`<span style="display:inline-flex;align-items:center;gap:6px"><span style="width:11px;height:11px;border-radius:3px;background:var(--hs3)"></span>25% DRAM budget</span>`+
    `<span style="display:inline-flex;align-items:center;gap:6px"><span style="width:11px;height:11px;border-radius:3px;background:var(--hs2);opacity:.85"></span>PMEM spill (75%)</span>`;
  host.appendChild(s);host.appendChild(lg);
}

// gap with vs without VMem: 4 bars/bench (all-DRAM & all-PMEM, native solid / VMem faded)
function drawGap(){
  const G=D.gap_compare||[]; if(!G.length){return;}
  const W=920,mL=42,mR=12,mT=12,mB=50,gGap=30;
  const maxV=Math.max(2.6,...G.flatMap(b=>b.bars.map(r=>r.x)))*1.08;
  const H=250,pW=W-mL-mR,pH=H-mT-mB,nb=G.length,gW=(pW-gGap*nb)/nb;
  const s=svg(W,H),Y=v=>mT+pH*(1-v/maxV);
  for(let g=0;g<=maxV;g+=0.5){
    s.appendChild(el('line',{x1:mL,x2:mL+pW,y1:Y(g),y2:Y(g),stroke:'var(--grid)','stroke-width':g===1?1.6:1,'stroke-dasharray':g===1?'5 4':''}));
    const t=el('text',{x:mL-6,y:Y(g)+3,'text-anchor':'end',fill:'var(--text-muted)','font-size':11});t.textContent=g.toFixed(1)+'×';s.appendChild(t);}
  G.forEach((b,bi)=>{const gx=mL+gGap/2+bi*(gW+gGap),n=b.bars.length,bw=Math.min(40,(gW-8)/n),pad=(gW-bw*n)/2;
    b.bars.forEach((r,i)=>{const x=gx+pad+i*bw,h=Math.max(2,pH*(r.x/maxV)),yy=mT+pH-h;
      const rc=el('rect',{x:x+2,y:yy,width:bw-4,height:h,rx:3,fill:`var(--${r.tier})`,opacity:r.dim?0.5:1,style:'cursor:pointer'});
      rc.addEventListener('mousemove',e=>showTip(e,`<b>${b.name} &middot; ${r.label}</b><br>${fmt(r.x)}× vs native all-DRAM<br>raw ${fmt(r.raw,r.raw>=100?0:2)}`));
      rc.addEventListener('mouseleave',hideTip);s.appendChild(rc);});
    const t=el('text',{x:gx+gW/2,y:H-30,'text-anchor':'middle',fill:'var(--text-primary)','font-size':13,style:'font-weight:600'});t.textContent=b.name;s.appendChild(t);
    const sub=el('text',{x:gx+gW/2,y:H-14,'text-anchor':'middle',fill:'var(--text-muted)','font-size':11});
    const sg=v=>(v>=0?'+':'')+v+'%';
    sub.textContent=`VMem vs numactl: all-DRAM ${sg(b.dram_diff)} · all-PMEM ${sg(b.pmem_diff)}`;s.appendChild(sub);});
  document.getElementById('fgap').appendChild(s);
}

// F1: grouped normalized bars + 95% CI error bars, from D.phase1 (extends per bench)
function drawF1(){
  const FIG=D.phase1||[]; if(!FIG.length){return;}
  document.getElementById('legF1').innerHTML=[['all-DRAM','hs3'],['first-touch 25%','hs4'],['VMem demote 25%','hs1'],['all-PMEM','hs2']]
    .map(c=>`<span style="display:inline-flex;align-items:center;gap:6px"><span style="width:11px;height:11px;border-radius:3px;background:var(--${c[1]})"></span>${c[0]}</span>`).join('');
  const W=920,mL=42,mR=12,mT=12,mB=54,gGap=26;
  const maxV=Math.max(1.15,...FIG.flatMap(b=>b.bars.map(r=>r.x+r.ci)))*1.06;
  const H=300,pW=W-mL-mR,pH=H-mT-mB,nb=FIG.length,gW=(pW-gGap*nb)/nb;
  const s=svg(W,H),Y=v=>mT+pH*(1-v/maxV);
  for(let g=0;g<=maxV;g+=0.5){
    s.appendChild(el('line',{x1:mL,x2:mL+pW,y1:Y(g),y2:Y(g),stroke:'var(--grid)','stroke-width':g===1?1.6:1,'stroke-dasharray':g===1?'5 4':''}));
    const t=el('text',{x:mL-6,y:Y(g)+3,'text-anchor':'end',fill:'var(--text-muted)','font-size':11});t.textContent=g.toFixed(1)+'×';s.appendChild(t);}
  FIG.forEach((b,bi)=>{
    const gx=mL+gGap/2+bi*(gW+gGap),n=b.bars.length,bw=Math.min(46,(gW-8)/Math.max(n,1)),pad=(gW-bw*n)/2;
    b.bars.forEach((r,i)=>{const x=gx+pad+i*bw,h=Math.max(2,pH*(r.x/maxV)),yy=mT+pH-h;
      const rc=el('rect',{x:x+2,y:yy,width:bw-4,height:h,rx:3,fill:`var(--${r.col})`,style:'cursor:pointer'});
      rc.addEventListener('mousemove',e=>showTip(e,`<b style="color:var(--${r.col})">${b.name} &middot; ${r.label}</b><br>${fmt(r.x)}× vs all-DRAM<br>raw ${fmt(r.raw,r.raw>=100?0:2)} &middot; n=${r.n}${r.ci?` &middot; ±${fmt(r.ci)}×`:''}<br><span style="color:var(--text-muted)">${r.note}</span>`));
      rc.addEventListener('mouseleave',hideTip);s.appendChild(rc);
      if(r.ci>0){const cx=x+bw/2;s.appendChild(el('line',{x1:cx,x2:cx,y1:Y(r.x-r.ci),y2:Y(r.x+r.ci),stroke:'var(--text-primary)','stroke-width':1.3,opacity:.5}));
        [r.x-r.ci,r.x+r.ci].forEach(v=>s.appendChild(el('line',{x1:cx-3,x2:cx+3,y1:Y(v),y2:Y(v),stroke:'var(--text-primary)','stroke-width':1.3,opacity:.5})));}
    });
    const t=el('text',{x:gx+gW/2,y:H-34,'text-anchor':'middle',fill:'var(--text-primary)','font-size':13,style:'font-weight:600'});t.textContent=b.name;s.appendChild(t);
    const sub=el('text',{x:gx+gW/2,y:H-18,'text-anchor':'middle',fill:'var(--text-muted)','font-size':11});
    sub.textContent=b.gap!=null?`gap ${b.gap}% · vmem ${b.vm_cap!=null?b.vm_cap+'%':'—'}`:'no all-PMEM';s.appendChild(sub);
  });
  document.getElementById('f1').appendChild(s);
}

// F8: gap-capture (first-touch vs vmem), only benches with a measured all-PMEM
function drawF8(){
  const FIG=(D.phase1||[]).filter(b=>b.gap!=null&&b.vm_cap!=null);
  document.getElementById('p1prov').textContent=
    `${(D.phase1||[]).length} benchmark(s): `+(D.phase1||[]).map(b=>b.name+(b.gap!=null?'':' (no all-PMEM)')).join(', ')+
    '. Raw metric units differ per benchmark; the × / % views are the comparable ones.';
  if(!FIG.length){document.getElementById('f8').innerHTML='<p class="muted">No benchmark has a measured all-PMEM endpoint yet.</p>';return;}
  const W=920,mL=38,mR=12,mT=14,mB=38,gGap=40,H=230,pW=W-mL-mR,pH=H-mT-mB,gW=(pW-gGap*FIG.length)/FIG.length;
  const s=svg(W,H),Y=v=>mT+pH*(1-v/100);
  [0,25,50,75,100].forEach(g=>{s.appendChild(el('line',{x1:mL,x2:mL+pW,y1:Y(g),y2:Y(g),stroke:'var(--grid)'}));
    const t=el('text',{x:mL-6,y:Y(g)+3,'text-anchor':'end',fill:'var(--text-muted)','font-size':11});t.textContent=g+'%';s.appendChild(t);});
  FIG.forEach((b,bi)=>{const gx=mL+gGap/2+bi*(gW+gGap),bw=Math.min(52,(gW-10)/2),pad=(gW-bw*2)/2;
    [['ft_cap','hs4','first-touch'],['vm_cap','hs1','VMem demote']].forEach((d,i)=>{
      const v=b[d[0]]||0,x=gx+pad+i*bw,h=Math.max(2,pH*(v/100)),yy=mT+pH-h;
      const rc=el('rect',{x:x+2,y:yy,width:bw-4,height:h,rx:3,fill:`var(--${d[1]})`,style:'cursor:pointer'});
      rc.addEventListener('mousemove',e=>showTip(e,`<b style="color:var(--${d[1]})">${b.name} &middot; ${d[2]}</b><br>captures ${v}% of the ${b.gap}% gap`));
      rc.addEventListener('mouseleave',hideTip);s.appendChild(rc);
      const vt=el('text',{x:x+bw/2,y:yy-5,'text-anchor':'middle',fill:`var(--${d[1]})`,'font-size':11,style:'font-weight:700'});vt.textContent=v+'%';s.appendChild(vt);});
    const t=el('text',{x:gx+gW/2,y:H-20,'text-anchor':'middle',fill:'var(--text-primary)','font-size':13,style:'font-weight:600'});t.textContent=b.name;s.appendChild(t);});
  document.getElementById('f8').appendChild(s);
}
build();
</script></body></html>
'''


# ---------------------------------------------------------------------------
# Section 0: the reviewer checklist. The specific questions a referee must see
# answered to accept "VMem works as a tiering system" for the NEXT paper (the
# MEMSYS'25 paper was a pure overhead study — no DRAM constraint, no demotion;
# this paper adds the constrained-DRAM tiering story). Edit status as work lands:
#   done | partial | active | open | blocked
# ---------------------------------------------------------------------------
REVIEW_LEAD = (
    "The original paper (VMem, MEMSYS&nbsp;2025) proved the substrate is <b>cheap</b> — it gave every "
    "benchmark enough local memory to hold its whole footprint and measured only fault overhead. This "
    "paper makes a different claim: that VMem <b>tiering actually works</b> under a constrained DRAM "
    "budget. These are the questions a reviewer needs answered to believe it. Status reflects the run "
    "harness in <code>vmem-sweep/phase1.sh</code>."
)
REVIEW_Q = [
    ("A. Does VMem work as a tiering system?", [
        ("Q1", "done" if False else "partial",
         "Does VMem recover the DRAM&rarr;PMEM placement gap?",
         "Placement ladder (Fig. below): demotion must claw back a large share of the all-DRAM&rarr;all-PMEM gap. LULESH: 63% of a 140% gap. AMG: re-running under the corrected footprint."),
        ("Q2", "partial",
         "Does tiering beat naive first-touch / OS spill?",
         "If DRAM-first-then-spill did as well, the OS would suffice. LULESH: demote 63% vs first-touch 12%. Need this across more workloads."),
        ("Q3", "partial",
         "What is promotion's role &mdash; does it add value beyond demotion?",
         "Honest characterization: so far promotion is inert on LULESH & graph500 (demotion is the workhorse). Either find a regime where it clearly helps, or explain why demotion carries the win."),
        ("Q4", "open",
         "Does the win hold across DRAM budgets, not one lucky point?",
         "DRAM-fraction sweep at 12.5 / 25 / 50% of footprint. Not started."),
        ("Q5", "partial",
         "Does it hold across diverse workloads &mdash; and are we honest about failures?",
         "Breadth (CORAL OpenMP + SPEC CPU FP) plus the known failure mode: gapbs random-access thrash under a constrained pool. LULESH + AMG so far."),
    ]),
    ("B. Is the comparison fair and the result real?", [
        ("Q6", "partial",
         "Is the substrate ~free when NOT tiering, on THIS machine + allocator?",
         "Re-establish the MEMSYS'25 overhead result on corsys4 (CLX+Optane): vmem-no-tier &asymp; native at both endpoints. LULESH endpoints match within &lt;0.1%; need it on more benches."),
        ("Q7", "active",
         "Is every condition apples-to-apples?",
         "Same substrate + allocator everywhere, DRAM capped identically, and footprint measured under the REAL 2&nbsp;MB pages (vmem peak-allocated-vpages) &mdash; not glibc RSS, which is blind to hugetlb and undercounts. This is the active fix."),
        ("Q8", "partial",
         "Does tiering preserve correctness (no silent corruption)?",
         "Stale-replica / write-protect corruption was root-caused and fixed (re-arm WP after UFFDIO_CONTINUE). Must show correct output for every app in the ladder, not just that it finishes."),
    ]),
    ("C. Decisions to lock since MEMSYS'25 (what changed)", [
        ("Q9", "done",
         "VMem now runs under a <b>standard</b> allocator (mimalloc), not a custom one.",
         "Deliberate change from the paper's custom bkmalloc: VMem deploys with an off-the-shelf, widely-used allocator &mdash; no custom allocator, no recompile &mdash; a stronger portability claim. Consequence we own, not a reason to switch back: mimalloc on 2&nbsp;MB pages inflates the footprint (worst for AMG's small-allocation pattern), so pools are sized from the measured vpage footprint (Q10), not glibc RSS."),
        ("Q10", "active",
         "How is footprint measured now?",
         "Peak allocated vpages under the 2&nbsp;MB substrate, accounting for large-page inflation (paper: ~18% avg for SPEC FP; AMG far worse). Replaces the native glibc-RSS method still in phase1.sh."),
        ("Q11", "done",
         "State the machine and tiers explicitly.",
         "Results are on corsys4 (CLX + Optane), tiering DRAM&harr;Optane &mdash; NOT the paper's 2&times;DDR5 SPR box (that node was lost). Bigger gap, different media; must be stated up front."),
    ]),
    ("D. Positioning vs prior art / bonus", [
        ("Q12", "open",
         "How does VMem compare to prior object-tiering (MAT Daemon)?",
         "Head-to-head vs the ISMM'22 object-tiering daemon (buildable at ~/projects/memory-ef/mat-daemon). Not started."),
        ("Q13", "blocked",
         "Does DSA accelerate migration (the SPR bonus)?",
         "Migration throughput memcpy vs DSA. Blocked on regaining Sapphire Rapids access; corsys4 has no DSA. A bonus, never a blocker."),
    ]),
]
_QLABEL = {"done": "answered", "partial": "partial", "active": "in&nbsp;progress",
           "open": "open", "blocked": "blocked"}


def review_html():
    out = [f'<section class="qwrap"><h2 style="margin-top:0">0. What a reviewer needs to see</h2>',
           f'<p class="qlead">{REVIEW_LEAD}</p>']
    for gtitle, items in REVIEW_Q:
        out.append(f'<div class="qgrp"><h3>{gtitle}</h3>')
        for qid, status, q, note in items:
            out.append(
                f'<div class="qitem"><div class="qid">{qid}</div>'
                f'<div><span class="qbadge qb-{status}">{_QLABEL[status]}</span></div>'
                f'<div><p class="qq">{q}</p><p class="qn">{note}</p></div></div>')
        out.append('</div>')
    out.append('</section>')
    return '\n'.join(out)


def main():
    import hashlib
    d = collect()
    if not d['migrate']['demote']:
        raise SystemExit('no migration results in %s -- run bench/run_bench.sh' % RES)
    if not d['mlc1']:
        raise SystemExit('no mlc 1-thread baseline; run copy_matrix --threads 1')
    html = TEMPLATE.replace('__REVIEW__', review_html())
    html = html.replace('__DATA__', json.dumps(d))
    html = html.replace('__BUILDID__', hashlib.md5(html.encode()).hexdigest()[:8])
    open(OUT, 'w').write(html)
    print('wrote %s (%d KB)' % (OUT, len(html) // 1024))
    for k in ('migrate', 'replicate', 'access'):
        for phase, v in d[k].items():
            if v:
                print(f'  {k:<10} {phase:<10} {v["mean"]:>9.3f}  spread {v["spread"]:.3f}  n={v["n"]}')


if __name__ == '__main__':
    main()
