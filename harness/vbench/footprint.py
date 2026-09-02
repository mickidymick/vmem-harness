"""Measure a benchmark's TRUE footprint: peak allocated vpages under the real
2 MB substrate, not glibc RSS (which is hugetlb-blind and undercounts).

Runs the app once through vmem with tiering OFF and oversized pools, so nothing
spills or gets reclaimed, then reads `peak allocated vpages` from VMEM_STATS.
"""
import os
import re
import shlex
import subprocess
from . import config
from .server import Server


def _parse_peak(text):
    m = re.search(r"peak allocated vpages:\s*(\d+)", text)
    return int(m.group(1)) if m else None


def contexts(stats_base):
    """Every vmem context that dumped stats for this run, as (peak_vpages, path).

    The runtime writes one file per pid ("<base>.<pid>"), because any process that
    inherits our LD_PRELOAD is also a vmem client -- an MPI-linked app run direct
    still has OpenMPI exec a singleton helper that connects, allocates ~nothing,
    and used to truncate the real stats on its way out. The application is the
    context with the largest peak. Falls back to the bare path for older libs.
    """
    found = []
    for p in sorted(stats_base.parent.glob(stats_base.name + ".*")):
        peak = _parse_peak(p.read_text(errors="ignore"))
        if peak is not None:
            found.append((peak, p))
    if not found and stats_base.exists():
        peak = _parse_peak(stats_base.read_text(errors="ignore"))
        if peak is not None:
            found.append((peak, stats_base))
    return sorted(found, reverse=True)


def measure(bench, machine, out_dir, args_override=None):
    """Measure peak vpages. With args_override the result is NOT saved -- that path
    is for sizing a smoke input, and must never overwrite the paper-scale footprint
    the real conditions are sized from."""
    b = config.bench(bench)
    name = b["name"]
    V = machine["vmem_repo"]
    cap = machine["pool_cap_vpages"]
    args = shlex.split(args_override or b.get("measure_args") or b["args"])

    server = Server(machine)
    server.start(cap, cap, out_dir / f"measure_{name}_srv.log")   # oversized: never spill
    lib = V / machine["libs"]["base"]
    stats = out_dir / f"measure_{name}.stats"
    log = out_dir / f"measure_{name}.log"
    cmd = ["timeout", "-k", "30", "9000",
           "sudo", "-E", "env", f"LD_LIBRARY_PATH={V}/lib:/usr/lib64",
           "env", f"LD_PRELOAD={lib}",
           f"VMEM_SOCKET_NAME={server.socket}", "VMEM_VREGIONS=1",
           f"OMP_NUM_THREADS={machine['omp_threads']}",
           "VMEM_STATS=1", f"VMEM_STATS_FILE={stats}",
           "VMEM_REPL_INTERVAL_MS=0", "VMEM_PROMO_INTERVAL_MS=0"]
    cmd += [str(b["exe"])] + args
    try:
        with open(log, "w") as f:
            subprocess.run(cmd, cwd=str(b["run_dir"]), stdout=f,
                           stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    finally:
        server.stop()

    found = contexts(stats)
    if not found:
        raise RuntimeError(f"measure {name}: no 'peak allocated vpages' in {stats}.* (see {log})")
    vpages = found[0][0]
    if len(found) > 1:
        print(f"  {len(found)} vmem contexts dumped stats (helpers inherited LD_PRELOAD); "
              f"peaks: {', '.join(str(p) for p, _ in found)} -> taking {vpages}")
    gib = vpages * machine["vpage_bytes"] / 2**30
    if args_override is None:
        config.save_footprint(name, vpages,
                              provenance=f"args='{b.get('measure_args') or b['args']}'  ({gib:.2f} GiB)")
    return vpages, gib
