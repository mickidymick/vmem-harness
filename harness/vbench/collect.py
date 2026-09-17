"""Aggregate a run's results.tsv into a per-(bench,condition) summary.

Three blocks per benchmark, because a runtime number on its own is not a result:
  1. the timings     -- mean, 95% CI, value normalized to all-DRAM, gap capture
  2. tiering evidence -- did the condition actually migrate anything?
  3. correctness      -- does the answer still match the all-DRAM reference?

A fast run that tiered nothing, or tiered and returned the wrong answer, has to be
visible here without anyone remembering to go and look at the .stats files.
"""
import statistics as st

from . import config

ORDER = ["all_dram", "mimalloc_dram", "vmem_dram", "first_touch", "profile_only",
         "vmem_demote", "demote_promote", "vmem_pmem", "all_pmem"]

# Two-sided 95% t multipliers by degrees of freedom. At the n=3..5 these sweeps run,
# the normal z=1.96 understates the interval badly (n=3 -> 4.30, not 1.96).
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
        6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _isum(rows, key):
    vals = [int(r[key]) for r in rows if r.get(key, "-") not in ("-", "", None)]
    return sum(vals) if vals else None


def _ci95(xs):
    if len(xs) < 2:
        return 0.0
    return _T95.get(len(xs) - 1, 1.96) * st.stdev(xs) / len(xs) ** 0.5


def load(tsv_path):
    """bench -> condition -> [row dicts]. Reads the '#' header so columns can grow
    without touching this; falls back to the original 4-column layout."""
    out, cols = {}, None
    for line in open(tsv_path):
        line = line.rstrip("\n")
        if not line:
            continue
        if line.startswith("#"):
            cols = line[1:].split("\t")
            continue
        parts = line.split("\t")
        if cols is None:
            cols = ["bench", "condition", "repeat", "metric"]
        r = dict(zip(cols, parts))
        if "bench" in r and "condition" in r:
            out.setdefault(r["bench"], {}).setdefault(r["condition"], []).append(r)
    return out


def _timings(conds, order):
    """Returns (lines, base, means); base is the all-DRAM mean, or None."""
    means, per_cond = {}, []
    for c in order:
        xs = [v for v in (_f(r.get("metric")) for r in conds[c]) if v is not None]
        if xs:
            means[c] = st.mean(xs)
        per_cond.append((c, xs, len(conds[c]) - len(xs)))

    base = means.get("all_dram")
    lines = [f"  {'condition':<16}{'mean':>12}{'95%CI':>10}{'vs all-DRAM':>14}{'n':>4}"]
    for c, xs, crashed in per_cond:
        note = f"   ({crashed} CRASH)" if crashed else ""
        if not xs:
            lines.append(f"  {c:<16}{'ALL CRASHED':>12}{note}")
            continue
        rel = f"{means[c] / base:.3f}x" if base else "-"
        lines.append(f"  {c:<16}{means[c]:>12.3f}{_ci95(xs):>10.3f}"
                     f"{rel:>14}{len(xs):>4}{note}")
    return lines, base, means


def _capture(means, base):
    if not base or "all_pmem" not in means:
        return []
    gap = means["all_pmem"] - base
    if gap <= 0:
        return [f"  -> all_pmem is not slower than all_dram (gap {gap:.3f}); "
                f"no placement gap to capture at this scale"]
    frag = [f"gap {100 * gap / base:.0f}%"]
    for c in ("vmem_dram", "first_touch", "profile_only", "vmem_demote", "demote_promote"):
        if c in means:
            frag.append(f"{c} captures {100 * (means['all_pmem'] - means[c]) / gap:.0f}%")
    return ["  -> " + " | ".join(frag)]


def _evidence(conds, order):
    """Did each condition actually do what its name claims?"""
    lines, any_vmem = [], False
    for c in order:
        rows = conds[c]
        rep, inv = _isum(rows, "replicas"), _isum(rows, "invalidated")
        ev, promo = _isum(rows, "evictions"), _isum(rows, "promos")
        if rep is None:
            continue                     # native condition: no vmem, nothing to prove
        any_vmem = True
        waste = f"{100 * inv / rep:.0f}%" if rep and inv is not None else "-"
        yld = f"{100 * ev / rep:.0f}%" if rep and ev is not None else "-"
        flag = ""
        if c in ("vmem_demote", "demote_promote") and not ev:
            flag = "   *** NO EVICTIONS — tiering did not happen ***"
        if c in ("first_touch", "vmem_dram", "vmem_pmem", "profile_only") and (rep or ev):
            flag = "   *** MIGRATED — this condition should have tiering OFF ***"
        lines.append(f"    {c:<16} replicas {rep:>7}  invalidated {waste:>5}  "
                     f"evictions {ev if ev is not None else '-':>7} ({yld:>4} of replicas)"
                     f"  promos {promo if promo is not None else '-':>6}{flag}")
    ctx = {int(r["stats_contexts"]) for rows in conds.values() for r in rows
           if r.get("stats_contexts", "-") not in ("-", "", None)}
    if any(n > 1 for n in ctx):
        lines.append(f"    note: {max(ctx)} vmem contexts per run — a helper process "
                     f"inherited LD_PRELOAD and is also a client (MPI-linked binary)")
    return (["  tiering evidence (application context, summed over repeats):"] + lines
            if any_vmem else [])


def _checked(row, names):
    """{check name: value} for one row. Rows carry "name=value;name=value"; rows from
    before multi-check support carry one bare float in `correctness_value`, which
    belongs to the bench's first (only) check."""
    raw = row.get("correctness", row.get("correctness_value"))
    if raw in (None, "", "-"):
        return {}
    if "=" not in raw:
        v = _f(raw)
        return {names[0] if names else "value": v} if v is not None else {}
    out = {}
    for part in raw.split(";"):
        k, _, v = part.partition("=")
        if _f(v) is not None:
            out[k] = _f(v)
    return out


def _correctness(conds, order, checks):
    names = [c["name"] for c in checks]
    tol = {c["name"]: c["tolerance"] for c in checks}
    dram = next((d for d in (_checked(r, names) for r in conds.get("all_dram", [])) if d), {})
    # Reference per check: a pinned `expect`, else the all_dram run's value.
    ref = {c["name"]: c["expect"] for c in checks if c.get("expect") is not None}
    ref.update({n: v for n, v in dram.items() if n not in ref})
    if not ref:
        return []
    src = {n: ("expect" if any(c["name"] == n and c.get("expect") is not None for c in checks)
               else "all_dram") for n in ref}
    lines = ["  correctness (max relative diff from reference, per check):",
             "    reference        " + "  ".join(
                 f"{n} {v:.8g} [{src[n]}, tol {tol.get(n, 1e-9):g}]" for n, v in ref.items())]
    for c in order:
        if all(r.get("metric") == "CRASH" for r in conds[c]):
            lines.append(f"    {c:<16} no value — every run crashed (see timings)")
            continue
        rows = [_checked(r, names) for r in conds[c]]
        parts, bad = [], False
        for n, rv in ref.items():
            vals = [d[n] for d in rows if n in d]
            if not vals:
                parts.append(f"{n} NO VALUE")
                bad = True
                continue
            worst = max(abs(v - rv) / abs(rv) if rv else abs(v) for v in vals)
            ok = worst <= tol.get(n, 1e-9)
            bad = bad or not ok
            parts.append(f"{n} {worst:.2e}{'' if ok else ' (over tol)'}")
        verdict = "*** MISMATCH ***" if bad else "ok"
        lines.append(f"    {c:<16} " + "  ".join(parts) + f"   {verdict}")
    return lines


def summarize(data, run_dir=None):
    out = []
    for bench, conds in data.items():
        order = [c for c in ORDER if c in conds] + [c for c in conds if c not in ORDER]
        checks = config.correctness_checks(config.bench_spec(bench, run_dir))
        out.append(f"\n{bench}")
        lines, base, means = _timings(conds, order)
        out += lines
        out += _capture(means, base)
        out += _evidence(conds, order)
        out += _correctness(conds, order, checks)
    return "\n".join(out)
