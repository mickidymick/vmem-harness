"""Config + discovery. Everything the harness knows comes from YAML under
configs/ and each benchmark's bench.yaml — no facts hardcoded in Python.

Paths are all relative to the harness dir, so the whole vmem-work tree can move
without editing anything here.
"""
import os
import yaml
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent      # .../vmem-work/harness
CONFIGS = HARNESS / "configs"
BENCH_DIR = HARNESS.parent / "benchmarks"             # .../vmem-work/benchmarks
RESULTS_DIR = HARNESS.parent / "results"


def _load(path):
    with open(path) as f:
        return yaml.safe_load(f)


def machine():
    m = _load(CONFIGS / "machine.yaml")
    m["vmem_repo"] = Path(os.path.expanduser(m["vmem_repo"])).resolve()
    return m


def conditions():
    return _load(CONFIGS / "conditions.yaml")


def knobs():
    return _load(CONFIGS / "knobs.yaml")


def experiment(name):
    return _load(CONFIGS / "experiments" / f"{name}.yaml")


def list_benches():
    """Discover benchmarks: any benchmarks/<name>/bench.yaml."""
    return sorted(p.parent.name for p in BENCH_DIR.glob("*/bench.yaml"))


def bench(name):
    """Load one benchmark record, with paths resolved to absolutes."""
    d = BENCH_DIR / name
    b = _load(d / "bench.yaml")
    b["dir"] = d
    b["run_dir"] = d / "run"
    b["exe"] = (d / b["exe"]).resolve()
    if not b["exe"].exists():
        raise FileNotFoundError(f"{name}: exe not found at {b['exe']}")
    return b


def bench_spec(name, run_dir=None):
    """The raw bench.yaml, preferring the snapshot a run saved of it -- so re-collecting
    an old run judges it by the tolerances it ran with, not today's file. None if
    neither exists."""
    if run_dir is not None:
        snap = Path(run_dir) / f"bench-{name}.yaml"
        if snap.exists():
            return _load(snap)
    path = BENCH_DIR / name / "bench.yaml"
    return _load(path) if path.exists() else None


def correctness_checks(spec):
    """A bench's correctness checks as a list of {name, metric, tolerance, expect}.

    bench.yaml may give one mapping (the original form) or a list. Tolerance is the
    max relative difference from the reference; it defaults to 1e-9, which only
    suits deterministic outputs -- a solver residual that varies with OpenMP
    reduction order needs its own. The reference is the all_dram run of the same
    sweep, unless the check pins `expect` (e.g. a validator's exit code, where
    all_dram failing too must not count as agreement)."""
    c = (spec or {}).get("correctness")
    if not c:
        return []
    items = c if isinstance(c, list) else [c]
    checks = []
    for i, item in enumerate(items):
        if not item.get("metric"):
            continue
        default = "value" if len(items) == 1 else f"check{i + 1}"
        checks.append({"name": item.get("name") or default,
                       "metric": item["metric"],
                       "tolerance": float(item.get("tolerance", 1e-9)),
                       "source": item.get("source"),
                       "reduce": item.get("reduce", "first"),
                       "expect": (float(item["expect"]) if item.get("expect") is not None
                                  else None)})
    return checks


# Measured footprint is DERIVED data, not config — it lives in a generated file so
# the hand-written, commented bench.yaml is never rewritten. `vbench measure` writes
# it; the runner reads it to size pools.
def footprint(name):
    """Measured peak-allocated-vpages for a bench, or None if not measured yet."""
    path = BENCH_DIR / name / "run" / "footprint.txt"
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return int(line.split()[0])
    return None


def save_footprint(name, vpages, provenance=""):
    path = BENCH_DIR / name / "run" / "footprint.txt"
    path.write_text(f"# measured peak allocated vpages (vbench measure)\n"
                    f"# {provenance}\n{vpages}\n")
