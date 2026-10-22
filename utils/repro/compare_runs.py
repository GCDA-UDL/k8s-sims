# -*- coding: utf-8 -*-
"""Compare two result folders of pipe-delimited <sim>.csv files.

For every simulator and node count it prints the mean of each metric in the
reference and in the candidate run, and the relative difference. Use it to
check that a re-run on another host reproduces the published results:

  python3 utils/repro/compare_runs.py results-repro/benchmark-all \
                                      results-repro/benchmark-myhost-20261022

Timing and resource metrics depend on the host, so they are only reported.
Rows are flagged with "!" when the mean unscheduled pods differ by more than
--pods-tol pods or a resource metric differs by more than --rel-tol.
Exit status is 1 when a simulator of the reference is missing or empty in the
candidate run.
"""
import argparse, csv, glob, os, sys
from collections import defaultdict

METRICS = ["run_time", "total_cpu_seconds", "memory_peak_gb", "unscheduled_pods"]


def load(folder):
    """sim -> node_count -> metric -> mean."""
    out = {}
    for path in sorted(glob.glob(os.path.join(folder, "*.csv"))):
        sim = os.path.splitext(os.path.basename(path))[0]
        rows = defaultdict(list)
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="|"):
                try:
                    rows[int(float(r["node_count"]))].append(r)
                except (KeyError, ValueError, TypeError):
                    continue
        agg = {}
        for n, rs in rows.items():
            agg[n] = {"runs": len(rs)}
            for m in METRICS:
                vals = []
                for r in rs:
                    try:
                        vals.append(float(r[m]))
                    except (KeyError, ValueError, TypeError):
                        pass
                agg[n][m] = sum(vals) / len(vals) if vals else float("nan")
        out[sim] = agg
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reference")
    ap.add_argument("candidate")
    ap.add_argument("--rel-tol", type=float, default=0.5,
                    help="relative difference that flags a resource metric (default 0.5)")
    ap.add_argument("--pods-tol", type=float, default=5,
                    help="unscheduled-pod difference that flags a row (default 5)")
    a = ap.parse_args()
    ref, cand = load(a.reference), load(a.candidate)
    if not ref:
        sys.exit("No CSVs in " + a.reference)

    missing = []
    print(f"{'sim':12s} {'nodes':>5s} {'runs':>9s}  " +
          "  ".join(f"{m:>30s}" for m in METRICS))
    for sim in sorted(ref):
        if not cand.get(sim):
            missing.append(sim)
            print(f"{sim:12s} MISSING in candidate")
            continue
        for n in sorted(ref[sim]):
            r, c = ref[sim][n], cand[sim].get(n)
            if c is None:
                missing.append(f"{sim}@{n}")
                print(f"{sim:12s} {n:5d} node count MISSING in candidate")
                continue
            cells, flag = [], False
            for m in METRICS:
                rv, cv = r[m], c[m]
                if m == "unscheduled_pods":
                    d = cv - rv
                    flag |= abs(d) > a.pods_tol
                    cells.append(f"{rv:9.1f} -> {cv:9.1f} ({d:+7.1f})")
                else:
                    rel = (cv - rv) / rv if rv else (0.0 if cv == rv else float("inf"))
                    flag |= abs(rel) > a.rel_tol and max(rv, cv) >= 1
                    cells.append(f"{rv:9.2f} -> {cv:9.2f} ({rel:+6.0%})")
            print(f"{sim:12s} {n:5d} {r['runs']:>4d}/{c['runs']:<4d}  " +
                  "  ".join(f"{x:>30s}" for x in cells) + ("  !" if flag else ""))
    extra = sorted(set(cand) - set(ref))
    if extra:
        print("Only in candidate:", ", ".join(extra))
    if missing:
        print("Missing:", ", ".join(missing))
        sys.exit(1)


if __name__ == "__main__":
    main()
