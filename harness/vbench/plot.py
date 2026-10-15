"""Figures for a sweep's results.tsv (all_dram / first_touch / vmem_demote).

    python3 -m vbench.plot <run_dir>      -> <run_dir>/figures/*.png, *.pdf
"""
import csv
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#ffffff"
VMEM, FT, DRAM = "#2a78d6", "#b9b7ae", "#52514e"   # vmem = the one colored series

NAMES = {"lulesh": "LULESH", "roms_s": "roms", "qmcpack": "QMCPACK", "snap": "SNAP",
         "cactubssn_s": "cactuBSSN", "fotonik3d_s": "fotonik3d", "bwaves_s": "bwaves",
         "amg": "AMG", "lbm_s": "lbm", "warpx": "WarpX", "gapbs_bfs": "GAPBS bfs",
         "gapbs_pr": "GAPBS pr"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "text.color": INK,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.spines.top": False,
    "axes.spines.right": False, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.dpi": 200, "savefig.bbox": "tight",
})


def verdicts(run_dir):
    """(bench, condition) -> True/False from the correctness block of SUMMARY.txt."""
    v, bench = {}, None
    for line in (run_dir / "SUMMARY.txt").read_text().splitlines():
        if line and not line.startswith(" "):
            bench = line.strip()
        m = re.match(r"\s+(\w+)\s+.*\s(ok|\*\*\* MISMATCH \*\*\*)$", line)
        if bench and m and "replicas" not in line:
            v[(bench, m.group(1))] = m.group(2) == "ok"
    return v


def load(run_dir):
    ver = verdicts(run_dir)
    rows = {}
    with open(run_dir / "results.tsv") as f:
        for r in csv.DictReader((l.lstrip("#") for l in f), delimiter="\t"):
            rows.setdefault(r["bench"], {})[r["condition"]] = r
    out = []
    for b, c in rows.items():
        t = {k: float(v["metric"]) for k, v in c.items()}
        gap = t["first_touch"] - t["all_dram"]
        rec = (t["first_touch"] - t["vmem_demote"]) / gap if gap > 0 else None
        ok = {k: v["rc"] == "0" and ver.get((b, k), False) for k, v in c.items()}
        out.append(dict(bench=b, name=NAMES.get(b, b), t=t, rec=rec, ok=ok,
                        checks={k: v["correctness"] for k, v in c.items()}))
    # recovered-most first; "no gap" last
    return sorted(out, key=lambda d: -999 if d["rec"] is None else d["rec"], reverse=True)


def save(fig, out, name):
    for ext in ("png", "pdf"):
        fig.savefig(out / f"{name}.{ext}")
    plt.close(fig)


def fig_slowdown(data, out, note):
    """Slowdown vs all-DRAM, first_touch vs vmem_demote, per benchmark."""
    fig, ax = plt.subplots(figsize=(11, 4.8))
    w = 0.38
    xs = range(len(data))
    ft = [d["t"]["first_touch"] / d["t"]["all_dram"] for d in data]
    vm = [d["t"]["vmem_demote"] / d["t"]["all_dram"] for d in data]
    ax.bar([x - w / 2 - 0.01 for x in xs], ft, w, color=FT, label="first-touch (tiering off)")
    ax.bar([x + w / 2 + 0.01 for x in xs], vm, w, color=VMEM, label="vmem demotion")
    ax.axhline(1, color=DRAM, lw=1.2, ls="--", zorder=3)
    ax.text(len(data) - 0.5, 1.03, "all-DRAM", ha="right", va="bottom", color=INK2, fontsize=9)
    ax.set_yscale("log")
    ax.set_yticks([1, 2, 4, 8, 12])
    ax.set_yticklabels(["1×", "2×", "4×", "8×", "12×"])
    ax.set_ylim(0.8, 14)
    ax.grid(axis="x", visible=False)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([d["name"] for d in data], rotation=30, ha="right")
    ax.set_ylabel("runtime ÷ all-DRAM runtime (log)")
    for x, d, f, v in zip(xs, data, ft, vm):
        if d["rec"] is not None and d["rec"] >= 0.25:
            ax.text(x + w / 2, v * 1.06, f"{v:.2f}×", ha="center", va="bottom",
                    fontsize=9, color=INK, fontweight="bold")
            ax.text(x - w / 2, f * 1.06, f"{f:.1f}×", ha="center", va="bottom",
                    fontsize=9, color=INK2)
    ax.legend(frameon=False, loc="upper right", ncol=2, bbox_to_anchor=(1, 1.12))
    ax.set_title("Slowdown at 25% DRAM, paper-scale inputs", loc="left",
                 fontweight="bold", pad=24)
    fig.text(0.01, -0.04, note, color=MUTED, fontsize=8.5)
    save(fig, out, "f1_slowdown")


def fig_recovery(data, out, note):
    """Share of the first-touch penalty that vmem demotion wins back."""
    lo = -20
    fig, ax = plt.subplots(figsize=(8, 5.2))
    rows = list(reversed(data))
    ys = range(len(rows))
    for y, d in zip(ys, rows):
        if d["rec"] is None:
            ax.text(1, y, "no penalty to recover (first-touch ≈ all-DRAM)",
                    va="center", color=MUTED, fontsize=9)
            continue
        r = d["rec"] * 100
        col = VMEM if r >= 25 else FT
        ax.barh(y, max(r, lo), 0.66, color=col)
        lab = f"{r:.0f}%"
        if r < lo:
            lab += f" (clipped; only +{d['t']['vmem_demote'] - d['t']['first_touch']:.2f} s absolute)"
            ax.text(1.2, y, lab, va="center", color=INK2, fontsize=9)
        else:
            ax.text(max(r, 0) + 1.2, y, lab, va="center", fontsize=10,
                    color=INK if r >= 25 else INK2,
                    fontweight="bold" if r >= 25 else "normal")
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([d["name"] for d in rows])
    ax.set_xlim(lo, 100)
    ax.set_ylim(-0.7, len(rows) - 0.4)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("share of the first-touch penalty recovered by vmem demotion")
    ax.set_title("Where demotion pays", loc="left", fontweight="bold")
    fig.text(0.01, -0.06, "recovered = (first_touch − vmem) / (first_touch − all_DRAM)\n" + note,
             color=MUTED, fontsize=8.5)
    save(fig, out, "f2_recovery")


def fig_lulesh(data, out, note, bench="lulesh"):
    """The headline app: absolute runtimes, three conditions."""
    d = next(x for x in data if x["bench"] == bench)
    conds = [("all_dram", "all-DRAM", DRAM), ("first_touch", "first-touch\n25% DRAM", FT),
             ("vmem_demote", "vmem demotion\n25% DRAM", VMEM)]
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    vals = [d["t"][c] for c, _, _ in conds]
    ax.bar(range(3), vals, 0.6, color=[c for _, _, c in conds])
    for x, v in enumerate(vals):
        ax.text(x, v + max(vals) * 0.015, f"{v:,.0f} s", ha="center", va="bottom",
                fontsize=11, fontweight="bold" if x == 2 else "normal")
    ax.set_xticks(range(3))
    ax.set_xticklabels([l for _, l, _ in conds])
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("runtime (s)")
    ax.set_ylim(0, max(vals) * 1.12)
    ax.set_title(f"{d['name']}: {d['rec'] * 100:.0f}% of the tiering penalty recovered",
                 loc="left", fontweight="bold")
    fig.text(0.01, -0.04, note, color=MUTED, fontsize=8.5)
    save(fig, out, f"f3_{bench}")


def fig_correctness(data, out, note):
    """Pass grid: every benchmark x condition, with the check it passed."""
    conds = ["all_dram", "first_touch", "vmem_demote"]
    data = sorted(data, key=lambda d: d["name"].lower())
    fig, ax = plt.subplots(figsize=(8.6, 0.42 * len(data) + 1.3))
    ax.set_xlim(-0.5, len(conds) + 1.6)
    ax.set_ylim(len(data) - 0.5, -1.4)
    ax.axis("off")
    for j, c in enumerate(conds):
        ax.text(j, -0.85, c.replace("_", "-"), ha="center", fontweight="bold", color=INK2)
    ax.text(len(conds) - 0.4, -0.85, "check", ha="left", fontweight="bold", color=INK2)
    for i, d in enumerate(data):
        if i % 2 == 0:
            ax.axhspan(i - 0.5, i + 0.5, color="#f4f3ef", zorder=0)
        ax.text(-0.55, i, d["name"], ha="right", va="center")
        for j, c in enumerate(conds):
            good = d["ok"][c]
            ax.text(j, i, "✓" if good else "✗", ha="center", va="center", fontsize=14,
                    color="#0ca30c" if good else "#d03b3b", fontweight="bold")
        chk = d["checks"]["vmem_demote"].split(";")
        chk = ", ".join(s.split("=")[0] for s in chk)
        ax.text(len(conds) - 0.4, i, chk, ha="left", va="center", color=MUTED, fontsize=9)
    n = sum(d["ok"][c] for d in data for c in conds)
    ax.set_title(f"Correctness at paper scale: {n}/{len(data) * len(conds)} runs pass",
                 loc="left", fontweight="bold", pad=14)
    fig.text(0.01, 0.0, note, color=MUTED, fontsize=8.5)
    save(fig, out, "f4_correctness")


def main(argv):
    run_dir = Path(argv[1])
    out = run_dir / "figures"
    out.mkdir(exist_ok=True)
    data = load(run_dir)
    note = f"corsys4 (CLX + Optane), one run per bar · {run_dir.name}"
    fig_slowdown(data, out, note)
    fig_recovery(data, out, note)
    fig_lulesh(data, out, note)
    fig_correctness(data, out, note)
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv)
