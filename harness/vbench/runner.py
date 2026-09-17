"""Run ONE (bench, condition, repeat) and return a result record.

Two paths, chosen by the condition's `kind`:
  native : numactl --membind to a node, no vmem. The reference endpoints.
  vmem   : size the pools from the measured footprint, start a server, run the app
           under the vmem substrate (LD_PRELOAD + tiering knobs), stop the server.

Single-process OpenMP apps run DIRECT — never under mpirun, which binds the lone
rank to one core and throttles OpenMP ~5x.
"""
import os
import re
import shlex
import shutil
import subprocess
import time
from . import config
from .footprint import contexts

# The counters that say whether tiering ACTUALLY happened. A vmem_demote run that
# migrated nothing is indistinguishable from first_touch by runtime alone, so every
# run carries its own proof that the variable was manipulated.
_STAT_FIELDS = {
    "replicas": r"replicas created:\s*(\d+)",
    "invalidated": r"replicas invalidated:\s*(\d+)",
    "candidates": r"eviction candidates:\s*(\d+)",
    "evictions": r"evictions performed:\s*(\d+)",
    "promos": r"promo completed:\s*(\d+)",
    "peak_vpages": r"peak allocated vpages:\s*(\d+)",
}


def _parse_stats(stats_base):
    """Read the application's stats context (the largest peak; the rest are helpers
    that inherited LD_PRELOAD) and return the tiering counters."""
    found = contexts(stats_base)
    if not found:
        return {}
    text = found[0][1].read_text(errors="ignore")
    out = {"stats_contexts": len(found)}
    for key, pat in _STAT_FIELDS.items():
        m = re.search(pat, text)
        if m:
            out[key] = int(m.group(1))
    return out


def _clamp(v, cap):
    return max(1, min(int(round(v)), cap))


def _metric(log_text, regex, reduce):
    vals = [float(m) for m in re.findall(regex, log_text)]
    if not vals:
        return None
    return {"max": max, "min": min, "first": lambda xs: xs[0],
            "last": lambda xs: xs[-1]}[reduce](vals)


def _run(cmd, cwd, log_path, env=None, timeout=9000, stdin_path=None, stdout_path=None):
    """Run under the `timeout` wrapper (with a hard -k 30 kill). stdout and stderr go
    to log_path, unless the bench names a `stdout` file (SPEC validates the app's
    stdout byte for byte, so nothing else may land in it) -- then stderr alone goes
    to the log. Returns (wall seconds, exit code); the wall time covers the whole
    process, including vmem client init and teardown under the vmem conditions."""
    full = ["timeout", "-k", "30", str(timeout)] + cmd
    with open(log_path, "w") as log:
        stdin = open(stdin_path) if stdin_path else subprocess.DEVNULL
        stdout = open(stdout_path, "w") if stdout_path else log
        try:
            t0 = time.monotonic()
            rc = subprocess.run(full, cwd=str(cwd), env=env, stdout=stdout,
                                stderr=log if stdout_path else subprocess.STDOUT,
                                stdin=stdin).returncode
            wall = time.monotonic() - t0
        finally:
            if stdin_path:
                stdin.close()
            if stdout_path:
                stdout.close()
    return wall, rc


def prepare_outputs(b):
    """Delete the output files a bench writes into its run dir -- a crashed run must
    never be validated against the previous run's leftovers -- and return the
    (stdin, stdout) paths the bench declares, or None."""
    for o in outputs_of(b):
        if o.is_symlink() or o.exists():
            o.unlink()
    rd = b["run_dir"]
    return (rd / b["stdin"] if b.get("stdin") else None,
            rd / b["stdout"] if b.get("stdout") else None)


def bench_env(b):
    """Environment the bench itself needs (e.g. SPEC's OMP_STACKSIZE), applied to
    every condition alike so it is never a difference between them."""
    return {k: str(v) for k, v in (b.get("env") or {}).items()}


def reclaim_run_dir(b):
    """vmem conditions run the app under sudo (perf needs root), so everything it
    writes in run/ is root-owned -- and the next native run, as the user, can neither
    delete those outputs nor write into root-owned subdirectories. Hand the tree back.
    -h/-R without -L changes symlinks themselves, never the SPEC/QMCPACK data behind them."""
    subprocess.run(["sudo", "chown", "-hR", f"{os.getuid()}:{os.getgid()}", str(b["run_dir"])],
                   check=True)


def outputs_of(b):
    names = list(b.get("outputs") or [])
    if b.get("stdout") and b["stdout"] not in names:
        names.append(b["stdout"])
    return [b["run_dir"] / n for n in names]


def _source_text(b, log, source):
    """The text a metric/correctness regex reads: the run log, or -- when the bench
    writes its report to a file instead of stdout (SNAP's out.txt) -- that file in
    the run dir. A missing file reads as empty, so the regex finds nothing and the
    run is marked crashed rather than scored from a stale file."""
    p = b["run_dir"] / source if source else log
    return p.read_text(errors="ignore") if p.exists() else ""


def _validate(b, log):
    """Run the bench's `validate` shell command in its run dir, outside vmem, and
    append its output + exit status to the log, where correctness regexes see it."""
    r = subprocess.run(["bash", "-c", b["validate"]], cwd=str(b["run_dir"]),
                       capture_output=True, text=True)
    with open(log, "a") as f:
        f.write(f"\n===== vbench validate: {b['validate']}\n{r.stdout}{r.stderr}"
                f"VBENCH_VALIDATE_RC={r.returncode}\n")


def _pools(bench_name, cond, machine, fp=None):
    if fp is None:
        fp = config.footprint(bench_name)
    if fp is None:
        raise RuntimeError(f"{bench_name}: no footprint measured — run `vbench measure {bench_name}` first")
    dram, pmem = fp * cond["dram_frac"], fp * cond["pmem_frac"]
    # A silently clamped pool is a silently invalid condition: the run still finishes
    # and still reports a number, but it is no longer the fraction the ladder claims.
    # Fail loudly instead -- the fix is a smaller input or more hugepages, not a cap.
    caps = {"DRAM": machine["dram_cap_vpages"], "PMEM": machine["pmem_cap_vpages"]}
    for label, want in (("DRAM", dram), ("PMEM", pmem)):
        if round(want) > caps[label]:
            raise RuntimeError(
                f"{bench_name}: {label} pool wants {round(want)} vpages but the {label} cap is "
                f"{caps[label]} ({caps[label] * 2 // 1024} GB of hugepages). Footprint {fp} "
                f"vpages is too large for this condition — raise nr_hugepages on that node "
                f"and the cap in machine.yaml, or shrink the input.")
    return _clamp(dram, caps["DRAM"]), _clamp(pmem, caps["PMEM"])


def run_one(bench, cond_name, cond, repeat, machine, knobs, server, out_dir,
            args_override=None, footprint_override=None, overrides=None):
    b = config.bench(bench) if isinstance(bench, str) else bench
    # An experiment may override any bench.yaml field for a cheap variant (a smoke
    # input needs its own args AND, for SPEC, its own reference output to validate
    # against). footprint_vpages is not a bench field -- it sizes the pools.
    overrides = dict(overrides or {})
    footprint_override = overrides.pop("footprint_vpages", footprint_override)
    b = dict(b, **overrides)
    name = b["name"]
    tag = f"{name}_{cond_name}_r{repeat}"
    log = out_dir / f"{tag}.log"
    threads = machine["omp_threads"]
    args = shlex.split(args_override or b["args"])

    rec = {"bench": name, "condition": cond_name, "repeat": repeat, "tag": tag}

    stdin_path, stdout_path = prepare_outputs(b)

    if cond["kind"] == "native":
        env = dict(os.environ, OMP_NUM_THREADS=str(threads), **bench_env(b))
        cmd = ["numactl", f"--membind={cond['node']}", str(b["exe"])] + args
        wall, rc = _run(cmd, b["run_dir"], log, env=env,
                        stdin_path=stdin_path, stdout_path=stdout_path)

    elif cond["kind"] == "vmem":
        V = machine["vmem_repo"]
        dram, pmem = _pools(name, cond, machine, footprint_override)
        rec["dram_vpages"], rec["pmem_vpages"] = dram, pmem
        server.start(dram, pmem, out_dir / f"srv_{tag}.log")
        lib = V / machine["libs"][cond["lib"]]
        knob_env = knobs[cond["knobs"]]
        stats = out_dir / f"{tag}.stats"
        # sudo -E env LD_LIBRARY_PATH=... env LD_PRELOAD=... VARS ... exe args
        cmd = ["sudo", "-E", "env", f"LD_LIBRARY_PATH={V}/lib:/usr/lib64",
               "env", f"LD_PRELOAD={lib}",
               f"VMEM_SOCKET_NAME={server.socket}", "VMEM_VREGIONS=1",
               f"OMP_NUM_THREADS={threads}", "VMEM_STATS=1", f"VMEM_STATS_FILE={stats}",
               # vmem's own status lines default to stdout, which is the app's output
               f"VMEM_DEBUG_FILE={out_dir / f'{tag}.vmem.log'}"]
        cmd += [f"{k}={v}" for k, v in knob_env.items()]
        cmd += [f"{k}={v}" for k, v in bench_env(b).items()]
        cmd += [str(b["exe"])] + args
        try:
            wall, rc = _run(cmd, b["run_dir"], log,
                            stdin_path=stdin_path, stdout_path=stdout_path)
        finally:
            server.stop()
            reclaim_run_dir(b)
        rec.update(_parse_stats(stats))
    else:
        raise ValueError(f"unknown condition kind: {cond['kind']}")

    rec["rc"] = rc
    for o in outputs_of(b):                # keep each run's outputs with its log
        if o.exists():
            shutil.copy(o, out_dir / f"{tag}.{o.name}")
    if b.get("validate"):
        _validate(b, log)

    text = log.read_text(errors="ignore")
    if b["metric"] == "wall":              # the bench prints no timer of its own
        rec["metric"] = wall if rc == 0 else None
    else:
        rec["metric"] = _metric(_source_text(b, log, b.get("metric_source")),
                                b["metric"], b.get("metric_reduce", "max"))
    # A nonzero exit is a crash even if a timer printed before the failure.
    if rc != 0 or "Assertion" in text or "Aborted" in text:
        rec["metric"] = None
    rec["crashed"] = rec["metric"] is None
    rec["correctness"] = {}
    for check in config.correctness_checks(b):
        v = _metric(_source_text(b, log, check.get("source")), check["metric"], check["reduce"])
        if v is not None:
            rec["correctness"][check["name"]] = v
    return rec
