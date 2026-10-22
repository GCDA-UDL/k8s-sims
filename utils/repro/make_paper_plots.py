# -*- coding: utf-8 -*-
"""Regenerate the paper's result figures from a unified big-sweep run (all six
simulators on one machine). Line plots use a LOG y-axis so kcs (~0.1 GB) and
Kubemark (~18 GB) are both legible; the confusing 0-1 CPU-ratio chart is replaced
by stacked user/system CPU-seconds bars.

Usage (from the repository root):
  python3 utils/repro/make_paper_plots.py --results results-repro/big-all --out figures-out
Needs: matplotlib (pip install matplotlib). CSVs are pipe-delimited with schema:
  node_count|pod_count|timeout_reached|mem_exceeded|run_time|total_cpu_seconds|
  user_cpu_seconds|system_cpu_seconds|memory_peak_gb|unscheduled_pods
"""
import argparse, csv, glob, os, sys
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# filename stem -> display label (and a stable plot order)
LABELS = {"opensim": "OpenSimulator", "kwok": "KWOK", "kube-sched": "Kube-sched",
          "simkube": "SimKube", "kubemark": "Kubemark", "kcs": "kcs"}
ORDER = ["kcs", "kwok", "opensim", "kube-sched", "simkube", "kubemark"]
FLOOR = {"memory_peak_gb": 0.01, "total_cpu_seconds": 0.5, "run_time": 0.5}  # log-axis floors


def load(results_dir):
    """sim -> {node_count -> averaged metrics dict}."""
    data = {}
    for path in glob.glob(os.path.join(results_dir, "*.csv")):
        if ".preserved-" in os.path.basename(path):
            continue
        sim = os.path.splitext(os.path.basename(path))[0]
        if sim not in LABELS:
            continue
        by_n = defaultdict(list)
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="|"):
                try:
                    by_n[int(float(r["node_count"]))].append(r)
                except (KeyError, ValueError):
                    continue
        agg = {}
        for n, rows in by_n.items():
            def mean(col, keep=lambda v: True):
                vals = []
                for r in rows:
                    try:
                        v = float(r[col])
                    except (KeyError, ValueError, TypeError):
                        continue
                    if keep(v):
                        vals.append(v)
                return sum(vals) / len(vals) if vals else 0.0
            pods = mean("pod_count")
            unsched = mean("unscheduled_pods")
            agg[n] = {
                "memory_peak_gb": mean("memory_peak_gb"),
                "total_cpu_seconds": mean("total_cpu_seconds"),
                "run_time": mean("run_time", keep=lambda v: v >= 0),  # drop -1 sentinel
                "user_cpu_seconds": mean("user_cpu_seconds"),
                "system_cpu_seconds": mean("system_cpu_seconds"),
                "success_rate": (1.0 - unsched / pods) if pods else 1.0,
            }
        if agg:
            data[sim] = agg
    return data


def line_plot(data, metric, ylabel, title, out_png, logy=True):
    plt.figure(figsize=(7, 4.2))
    floor = FLOOR.get(metric, 0)
    for sim in ORDER:
        if sim not in data:
            continue
        ns = sorted(data[sim])
        ys = [max(data[sim][n][metric], floor) if logy else data[sim][n][metric] for n in ns]
        plt.plot(ns, ys, marker="o", ms=3, label=LABELS[sim])
    if logy:
        plt.yscale("log")
    plt.xlabel("Node Count")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(True, which="both", ls=":", alpha=0.5)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    plt.close()
    print("wrote", out_png)


def stacked_cpu(data, out_png):
    """Absolute user vs system CPU seconds at the largest common node count (log y)."""
    common = set.intersection(*[set(data[s]) for s in data]) if data else set()
    n = max(common) if common else None
    sims = [s for s in ORDER if s in data and (n in data[s] if n else False)]
    if not sims:
        print("stacked_cpu: no common node count; skipped"); return
    labels = [LABELS[s] for s in sims]
    user = [max(data[s][n]["user_cpu_seconds"], 0.01) for s in sims]
    system = [max(data[s][n]["system_cpu_seconds"], 0.01) for s in sims]
    plt.figure(figsize=(7, 4.2))
    plt.bar(labels, user, label="user CPU")
    plt.bar(labels, system, bottom=user, label="system CPU")
    plt.yscale("log")
    plt.ylabel("CPU seconds (log)")
    plt.title(f"User vs. system CPU time at {n} nodes")
    plt.grid(True, axis="y", which="both", ls=":", alpha=0.5)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    plt.close()
    print("wrote", out_png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="dir with <sim>.csv files")
    ap.add_argument("--out", required=True, help="output dir (paper figures/results)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    data = load(a.results)
    if not data:
        sys.exit("No simulator CSVs found in " + a.results)
    print("loaded:", ", ".join(sorted(data)))
    o = lambda f: os.path.join(a.out, f)
    line_plot(data, "memory_peak_gb", "Peak memory (GB, log)",
              "Peak memory consumption vs. node count", o("memory_peak_gb_vs_node_count.png"))
    line_plot(data, "total_cpu_seconds", "Total CPU time (s, log)",
              "Total CPU time vs. node count", o("total_cpu_seconds_vs_node_count.png"))
    line_plot(data, "run_time", "Run time (s, log)",
              "Total simulation run time vs. node count", o("run_time_vs_node_count.png"))
    line_plot(data, "success_rate", "Scheduling success rate",
              "Scheduling success rate vs. node count",
              o("scheduling_success_rate_vs_node_count.png"), logy=False)
    stacked_cpu(data, o("cpu_user_system_stacked.png"))
    print("Done. Six-curve log plots + stacked CPU written to", a.out)


if __name__ == "__main__":
    main()
