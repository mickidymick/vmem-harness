"""The vbench CLI: verbs that compose the modules. Each verb does one thing.

  vbench list                                  benchmarks + conditions
  vbench measure <bench>                       measure footprint -> run/footprint.txt
  vbench run <bench> -c <cond> [-n N]          run one condition
  vbench sweep <experiment> [-n N]             run the benches x conditions matrix
  vbench collect <run-id>                      re-summarize a past run

Every run writes a fresh, timestamped results/<id>/ (its own logs, results.tsv,
SUMMARY.txt, and a snapshot of the config used) — runs never contaminate each other.
"""
import argparse
import datetime
import shutil
import subprocess

from . import collect, config
from . import footprint as fp
from .runner import run_one
from .server import Server


def _provenance(d):
    """Record exactly which vmem produced this run: commit, working-tree state, and
    the library build times. A result whose binaries cannot be identified after the
    fact cannot be defended in a paper -- and this tree carries an uncommitted
    server patch (the exact pool sizing), so the commit alone is not enough."""
    repo = config.machine()["vmem_repo"]

    def git(*a):
        r = subprocess.run(["git", "-C", str(repo)] + list(a),
                           capture_output=True, text=True)
        return r.stdout.rstrip()

    dirty = git("status", "--short")
    lines = [f"vmem repo:  {repo}",
             f"commit:     {git('rev-parse', 'HEAD')}",
             f"branch:     {git('rev-parse', '--abbrev-ref', 'HEAD')}",
             f"run at:     {datetime.datetime.now().isoformat(timespec='seconds')}",
             "",
             "uncommitted changes:",
             *(f"  {l}" for l in (dirty.splitlines() or ["(clean)"])),
             "",
             "libraries:"]
    for so in sorted((repo / "lib").glob("*.so")):
        ts = datetime.datetime.fromtimestamp(so.stat().st_mtime)
        lines.append(f"  {ts:%Y-%m-%d %H:%M}  {so.name}")
    (d / "PROVENANCE.txt").write_text("\n".join(lines) + "\n")
    if dirty:
        (d / "vmem-uncommitted.diff").write_text(git("diff") + "\n")


def _run_dir(label):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = config.RESULTS_DIR / f"{stamp}-{label}"
    d.mkdir(parents=True, exist_ok=True)
    _provenance(d)
    return d


# One row per run, with the evidence on the row: the metric is what we claim, the
# tiering counters are the proof the condition did what it says, and the correctness
# value is the proof the answer survived it. Column 4 stays the metric so the file is
# still readable by eye. Missing values are '-' (native conditions have no counters).
_COLUMNS = ["bench", "condition", "repeat", "metric", "correctness", "rc",
            "dram_vpages", "pmem_vpages", "replicas", "invalidated",
            "candidates", "evictions", "promos", "stats_contexts"]


def _append_tsv(out, rec):
    path = out / "results.tsv"
    if not path.exists():
        path.write_text("#" + "\t".join(_COLUMNS) + "\n")
    vals = []
    for c in _COLUMNS:
        v = rec.get(c)
        if c == "metric" and v is None:
            v = "CRASH"
        if c == "correctness":          # one cell, "name=value;name=value"
            v = ";".join(f"{k}={x}" for k, x in v.items()) if v else None
        vals.append("-" if v is None else str(v))
    with open(path, "a") as f:
        f.write("\t".join(vals) + "\n")


def _fmt(rec):
    v = "CRASH" if rec.get("crashed") else f"{rec['metric']:.3f}"
    extra = ""
    if "dram_vpages" in rec:
        extra = f"  [DRAM {rec['dram_vpages']} / PMEM {rec['pmem_vpages']}]"
    if "replicas" in rec:
        # live proof the condition tiered (or didn't), without waiting for the summary
        extra += f"  repl {rec['replicas']} evict {rec.get('evictions', '-')}"
    return f"  {rec['tag']:<32} {v:>12}{extra}"


def _snapshot_bench(out, name):
    """Save the bench.yaml and measured footprint a run used: the correctness
    tolerances and the pool sizes are both derived from them."""
    d = config.BENCH_DIR / name
    shutil.copy(d / "bench.yaml", out / f"bench-{name}.yaml")
    if (d / "run" / "footprint.txt").exists():
        shutil.copy(d / "run" / "footprint.txt", out / f"footprint-{name}.txt")


def _finish(out, recs):
    summary = collect.summarize(collect.load(out / "results.tsv"), run_dir=out)
    (out / "SUMMARY.txt").write_text(summary + "\n")
    print(summary)
    print(f"\n-> {out}")


def cmd_list(args):
    print("benchmarks:", ", ".join(config.list_benches()) or "(none)")
    print("conditions:", ", ".join(config.conditions()))
    for b in config.list_benches():
        print(f"  {b}: footprint {config.footprint(b) or '(unmeasured)'} vpages")


def cmd_measure(args):
    out = _run_dir(f"measure-{args.bench}")
    vpages, gib = fp.measure(args.bench, config.machine(), out, args_override=args.args)
    where = ("(not saved — args override; use this to size a smoke experiment)"
             if args.args else f"-> benchmarks/{args.bench}/run/footprint.txt")
    print(f"{args.bench}: {vpages} vpages ({gib:.2f} GiB) {where}")


def cmd_run(args):
    m, conds, kb = config.machine(), config.conditions(), config.knobs()
    if args.condition not in conds:
        raise SystemExit(f"unknown condition '{args.condition}' (have: {', '.join(conds)})")
    out = _run_dir(f"run-{args.bench}-{args.condition}")
    _snapshot_bench(out, args.bench)
    server = Server(m)
    recs = []
    for r in range(1, args.repeats + 1):
        rec = run_one(args.bench, args.condition, conds[args.condition], r, m, kb, server, out,
                      args_override=args.args)
        recs.append(rec)
        _append_tsv(out, rec)
        print(_fmt(rec))
    _finish(out, recs)


def cmd_sweep(args):
    m, conds, kb = config.machine(), config.conditions(), config.knobs()
    exp = config.experiment(args.experiment)
    out = _run_dir(f"sweep-{exp['name']}")
    # snapshot the exact config used, for reproducibility
    for f in ("conditions.yaml", "knobs.yaml", "machine.yaml"):
        shutil.copy(config.CONFIGS / f, out / f)
    shutil.copy(config.CONFIGS / "experiments" / f"{args.experiment}.yaml", out / "experiment.yaml")
    for bench in exp["benches"]:
        _snapshot_bench(out, bench)
    repeats = args.repeats or exp.get("repeats", 3)
    # Per-bench overrides let one experiment run a cheap variant of a benchmark: a
    # smoke input needs both its own args AND its own footprint, or the pools get
    # sized from the paper-scale measurement and the smoke stops testing anything.
    over = exp.get("overrides") or {}
    server = Server(m)
    recs = []
    for bench in exp["benches"]:
        ov = over.get(bench) or {}
        for cond_name in exp["conditions"]:
            for r in range(1, repeats + 1):
                rec = run_one(bench, cond_name, conds[cond_name], r, m, kb, server, out,
                              overrides=ov)
                recs.append(rec)
                _append_tsv(out, rec)
                print(_fmt(rec))
    _finish(out, recs)


def cmd_collect(args):
    tsv = config.RESULTS_DIR / args.run_id / "results.tsv"
    if not tsv.exists():
        raise SystemExit(f"no results.tsv in {tsv.parent}")
    print(collect.summarize(collect.load(tsv), run_dir=tsv.parent))


def main(argv=None):
    p = argparse.ArgumentParser(prog="vbench", description="vmem experiment harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="benchmarks + conditions").set_defaults(fn=cmd_list)

    s = sub.add_parser("measure", help="measure a benchmark's footprint")
    s.add_argument("bench")
    s.add_argument("-a", "--args", default=None,
                   help="measure a different input (e.g. a smoke size); result is NOT saved")
    s.set_defaults(fn=cmd_measure)

    s = sub.add_parser("run", help="run one benchmark x condition")
    s.add_argument("bench")
    s.add_argument("-c", "--condition", required=True)
    s.add_argument("-n", "--repeats", type=int, default=1)
    s.add_argument("-a", "--args", default=None, help="override the benchmark's args (e.g. a small smoke input)")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("sweep", help="run an experiment (benches x conditions x repeats)")
    s.add_argument("experiment")
    s.add_argument("-n", "--repeats", type=int, default=0, help="override experiment repeats")
    s.set_defaults(fn=cmd_sweep)

    s = sub.add_parser("collect", help="re-summarize a past run")
    s.add_argument("run_id")
    s.set_defaults(fn=cmd_collect)

    args = p.parse_args(argv)
    args.fn(args)
