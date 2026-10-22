# -*- coding: utf-8 -*-
"""Absolute-value benchmark bars (replaces the confusing 0-1 normalized chart):
4 panels (run time s, total CPU s, peak memory GB, unscheduled pods) across the
six simulators + vanilla, real units, log y for the magnitude metrics.

Usage (from the repository root; this is the bar figure of the paper):
  python3 utils/repro/make_benchmark_bars.py --results results-repro/benchmark-all \
      --out bars_run_time_total_cpu_seconds_memory_peak_gb_unscheduled_pods.png
"""
import csv, os, sys, argparse
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ap = argparse.ArgumentParser()
ap.add_argument("--results", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

ORDER = ["kcs", "opensim", "kwok", "kube-sched", "kubemark", "simkube", "vanilla"]
LABEL = {"kcs": "kcs", "opensim": "OpenSimulator", "kwok": "KWOK",
         "kube-sched": "Kube-sched", "kubemark": "Kubemark", "simkube": "SimKube",
         "vanilla": "vanilla"}

data = {}
for s in ORDER:
    f = os.path.join(a.results, s + ".csv")
    if not os.path.exists(f):
        continue
    cols = {"run_time": [], "total_cpu_seconds": [], "memory_peak_gb": [], "unscheduled_pods": []}
    for r in csv.DictReader(open(f, encoding="utf-8"), delimiter="|"):
        for k in cols:
            try:
                cols[k].append(float(r[k]))
            except (KeyError, ValueError, TypeError):
                pass
    if cols["run_time"]:
        data[s] = {k: (sum(v) / len(v) if v else 0.0) for k, v in cols.items()}

sims = [s for s in ORDER if s in data]
names = [LABEL[s] for s in sims]
colors = plt.cm.tab10(range(len(sims)))
panels = [("Run time (s)", "run_time", True),
          ("Total CPU time (s)", "total_cpu_seconds", True),
          ("Peak memory (GB)", "memory_peak_gb", True),
          ("Unscheduled pods", "unscheduled_pods", False)]

fig, axes = plt.subplots(2, 2, figsize=(10, 7))
for ax, (title, key, logy) in zip(axes.flat, panels):
    vals = [data[s][key] for s in sims]
    disp = [max(v, 0.01) if logy else v for v in vals]
    bars = ax.bar(names, disp, color=colors)
    if logy:
        ax.set_yscale("log")
    ax.set_title(title, fontsize=11)
    ax.tick_params(axis="x", rotation=40, labelsize=8)
    for lbl in ax.get_xticklabels():
        lbl.set_ha("right")
    ax.grid(True, axis="y", ls=":", alpha=0.5)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                (f"{v:.0f}" if v >= 1 else f"{v:.2f}"), ha="center", va="bottom", fontsize=7)
fig.suptitle("Small-scale benchmark (4 nodes, 400 pods): simulators vs. vanilla Kubernetes", fontsize=12)
plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig(a.out, dpi=150)
print("wrote", a.out, "| modules:", ", ".join(sims))
