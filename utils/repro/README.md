# Reproduction scripts

Scripts that re-run the published experiments and regenerate the figures from
the CSVs in [`results-repro/`](../../results-repro). Run them from the
repository root.

| Script | Purpose |
|---|---|
| [`run_sweep.sh`](run_sweep.sh) | Runs a dataset over a set of simulators in the runner container and writes `<sim>.csv`, `SIM_MODULES` and `RUN_INFO` (host, commit, image) to the output folder. |
| [`compare_runs.py`](compare_runs.py) | Compares a new run with a reference folder, per simulator and node count. |
| [`make_benchmark_bars.py`](make_benchmark_bars.py) | Bar figure of the small-scale benchmark (6 simulators + vanilla). |
| [`make_paper_plots.py`](make_paper_plots.py) | Line plots of the big sweep (6 simulators, 100–1200 nodes). |

## Reference results

| Folder | Dataset | Simulators | Runs | Host |
|---|---|---|---|---|
| `results-repro/benchmark-all` | `data/benchmark` (4 nodes, 400 pods) | opensim, kwok, kube-sched, simkube, kubemark, kcs, vanilla | 3 | 2× Xeon Silver 4210R (40 threads), 128 GB, Rocky Linux 9.3, cgroups v2; 2026-06-17 |
| `results-repro/big-all` | `data/big` (100–1200 nodes) | opensim, kwok, kube-sched, simkube, kubemark, kcs | 3 | same server, 2026-06-15/17 (opensim re-run after the cgroup fix) |

| Re-run | Result |
|---|---|
| `results-repro/benchmark-spoofing-20261022` (v0.3.0 pre-release, same server, same runner image) | All 7 configurations, 3/3 runs. Unscheduled pods: 0 for every tool except Kubemark (55–70 per run; 40–69 in `benchmark-all`). Run time, CPU time and peak memory within ±11 % for the tools that run longer than a few seconds; kcs and OpenSimulator (1–2 s, < 0.01 GB) match within the 1 s / 0.01 GB resolution. Full table: `COMPARE.txt`. |

Re-run on that server to compare absolute numbers. `run_sweep.sh` uses the
runner image already present on the host (`docker run` does not pull a newer
`:latest`) and records its image ID in `RUN_INFO`.

## Re-run the benchmark and compare

```bash
bash utils/repro/run_sweep.sh            # DATASET=benchmark, 7 modules, RUNS=3
python3 utils/repro/compare_runs.py results-repro/benchmark-all results-repro/benchmark-<host>-<date>
```

Run times and resource use depend on the host; the number of unscheduled pods
should match.

## Regenerate the figures

```bash
python3 utils/repro/make_benchmark_bars.py --results results-repro/benchmark-all \
    --out bars_run_time_total_cpu_seconds_memory_peak_gb_unscheduled_pods.png
python3 utils/repro/make_paper_plots.py --results results-repro/big-all --out figures-out
```

Requires `matplotlib`.
