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
import subprocess
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
    return {"max": max, "min": min, "first": lambda xs: xs[0]}[reduce](vals)


def _run(cmd, cwd, log_path, env=None, timeout=9000):
    """Run under the `timeout` wrapper (with a hard -k 30 kill), tee to log_path."""
    full = ["timeout", "-k", "30", str(timeout)] + cmd
    with open(log_path, "w") as log:
        subprocess.run(full, cwd=str(cwd), env=env, stdout=log,
                       stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)


def _pools(bench_name, cond, cap, fp=None):
    if fp is None:
        fp = config.footprint(bench_name)
    if fp is None:
        raise RuntimeError(f"{bench_name}: no footprint measured — run `vbench measure {bench_name}` first")
    dram, pmem = fp * cond["dram_frac"], fp * cond["pmem_frac"]
    # A silently clamped pool is a silently invalid condition: the run still finishes
    # and still reports a number, but it is no longer the fraction the ladder claims.
    # Fail loudly instead -- the fix is a smaller input or more hugepages, not a cap.
    for label, want in (("DRAM", dram), ("PMEM", pmem)):
        if round(want) > cap:
            raise RuntimeError(
                f"{bench_name}: {label} pool wants {round(want)} vpages but the pool cap is "
                f"{cap} ({cap * 2 // 1024} GB of hugepages/node). Footprint {fp} vpages is too "
                f"large for this condition — shrink the input or raise nr_hugepages.")
    return _clamp(dram, cap), _clamp(pmem, cap)


def run_one(bench, cond_name, cond, repeat, machine, knobs, server, out_dir,
            args_override=None, footprint_override=None):
    b = config.bench(bench) if isinstance(bench, str) else bench
    name = b["name"]
    tag = f"{name}_{cond_name}_r{repeat}"
    log = out_dir / f"{tag}.log"
    threads = machine["omp_threads"]
    args = shlex.split(args_override or b["args"])

    rec = {"bench": name, "condition": cond_name, "repeat": repeat, "tag": tag}

    if cond["kind"] == "native":
        env = dict(os.environ, OMP_NUM_THREADS=str(threads))
        cmd = ["numactl", f"--membind={cond['node']}", str(b["exe"])] + args
        _run(cmd, b["run_dir"], log, env=env)

    elif cond["kind"] == "vmem":
        V = machine["vmem_repo"]
        dram, pmem = _pools(name, cond, machine["pool_cap_vpages"], footprint_override)
        rec["dram_vpages"], rec["pmem_vpages"] = dram, pmem
        server.start(dram, pmem, out_dir / f"srv_{tag}.log")
        lib = V / machine["libs"][cond["lib"]]
        knob_env = knobs[cond["knobs"]]
        stats = out_dir / f"{tag}.stats"
        # sudo -E env LD_LIBRARY_PATH=... env LD_PRELOAD=... VARS ... exe args
        cmd = ["sudo", "-E", "env", f"LD_LIBRARY_PATH={V}/lib:/usr/lib64",
               "env", f"LD_PRELOAD={lib}",
               f"VMEM_SOCKET_NAME={server.socket}", "VMEM_VREGIONS=1",
               f"OMP_NUM_THREADS={threads}", "VMEM_STATS=1", f"VMEM_STATS_FILE={stats}"]
        cmd += [f"{k}={v}" for k, v in knob_env.items()]
        cmd += [str(b["exe"])] + args
        try:
            _run(cmd, b["run_dir"], log)
        finally:
            server.stop()
        rec.update(_parse_stats(stats))
    else:
        raise ValueError(f"unknown condition kind: {cond['kind']}")

    text = log.read_text(errors="ignore")
    rec["metric"] = _metric(text, b["metric"], b.get("metric_reduce", "max"))
    rec["crashed"] = "Assertion" in text or "Aborted" in text or rec["metric"] is None
    c = b.get("correctness") or {}
    if c.get("metric"):
        rec["correctness_value"] = _metric(text, c["metric"], "first")
    return rec
