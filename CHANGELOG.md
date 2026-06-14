# Changelog

All notable changes to the GCDA fork of k8s-sims. The original toolkit by
Matias Medina (TFG UdL 2025) is tagged **`v0.1`** and is the baseline below.

## [Unreleased] — GCDA (2026-06)

Continuation by GCDA (Grupo de Computación Distribuida y Avanzada), Universitat de Lleida of
Matias Medina's toolkit. Verified reproducibility, fixed a silent benchmark bug,
added two simulators and two trace sources. All work was validated on Docker
Desktop / WSL2 (cgroup v2); see `REPRODUCIBILITY_REPORT.md` for evidence.

### Phase 1 — reproducibility

- **Verified** the original benchmark is reproducible: all 5 published simulators
  (kwok, opensim, kube-sched, simkube, kubemark) run end-to-end and the headline
  trends of `summaries/summary.json` hold (kwok/opensim lightest, kubemark/simkube
  heaviest). Full report: `REPRODUCIBILITY_REPORT.md`.
- **Fixed (kubemark): silent scheduling failure.** The hollow-node kubeconfig kept
  `server: https://127.0.0.1:<port>` (the rewrite `sed` was commented out), so no
  fake node registered and every pod stayed Pending while the run still reported
  success. Un-commented the rewrite to the in-cluster Service endpoint; verified
  the hollow node registers and pods schedule (`modules/kubemark/module.sh`).
- **Added `.gitattributes`** forcing LF for shell/py/yaml/conf. The repo shipped
  CRLF with no `.gitattributes`; sourcing those files in the Alpine container from
  a Windows checkout broke them. (This was the only cause of the 2 transient bats
  failures observed.)
- Preserved the original reference summary as `summaries/summary.matias-big.json`.
- Evidence (CSVs, aggregated summary, 13 plots) under `results-repro/`.

### Phase 2 — new simulators (opt-in)

- **K8sSim (Volcano)** — `modules/k8ssim/`. The only simulator covering the
  **Volcano** scheduler (gang/DRF/SLA × LRP/MRP/BRA/BINPACK), closing a gap left
  by the five kube-scheduler-only simulators. Builds from pinned commit `7168cb3`
  (vendored Go). Includes a stdlib-only HTTP driver (`k8ssim_driver.py`) and the
  Volcano scheduling configs. The TFG marked K8sSim "not available" — it is public
  and builds/runs.
- **`kube-gen.py --k8ssim`** — emits the K8sSim Volcano dataset (Node → cluster
  entry, each bin-packed Pod → a Volcano Job) from the same Alibaba base data.
- **Volcano scheduler sweep** — all 20 Volcano configs over a 1067-job Alibaba
  dataset; results in `results-repro/k8ssim/VOLCANO_SWEEP.md`.
- **kcs (pfn k8s-cluster-simulator)** — `modules/kcs/`. Preferred Networks'
  discrete-event scheduler simulator (pinned commit `55e4108`, GOPATH/vendored).
  Custom Go entry point reads the toolkit's standard `pods-<N>.yaml` and
  synthesises pod execution; reuses the existing `vanilla` datasets (no new
  dataset format). Build via `modules/kcs/build.sh`.

### Datasets — new trace sources

- **`utils/trace-convert/`** — converters that emit the existing base manifest
  format, so every simulator and `kube-gen.py` consume them unchanged:
  - `borg2base.py` — Google Borg (`google/cluster-data`, ClusterData2011).
  - `azure2base.py` — Azure (`Azure/AzurePublicDataset` vmtable).
  - `samples/` — tiny synthetic CSVs in the documented schemas for offline tests.

### Assessed, not integrated

- **Q8S** (QEMU/OpenStack heterogeneous-cluster emulator) — infeasible on a
  WSL2/laptop host (needs KVM + OpenStack).
- **Reckon** (`AleSassi/reckon-k8s`) — runnable here (the OVS kernel module ships
  in the WSL2 kernel) but it is a network-fault / consensus-availability emulator,
  not a scheduler simulator, so it does not fit this benchmark's metric model.
  Rationale in `research_notes/.../16_reckon_q8s_feasibility.md` (survey workspace).

### Docs

- New: `REPRODUCIBILITY_REPORT.md`, `CHANGELOG.md`, per-module READMEs
  (`modules/k8ssim`, `modules/kcs`), `utils/trace-convert/README.md`.
- Updated: `README.md` (fork status + documentation map), `ARCHITECTURE.md`
  (structure, module table, generator, glossary), `SIM_MODULES.md` (k8ssim/kcs
  rows), `DATASETS.md` (trace sources), `modules/README.md`, `utils/README.md`.

## [v0.1] — Matias Medina (2025)

Original toolkit: 5 simulators (kwok, opensim, kube-sched, simkube, kubemark),
Alibaba-trace dataset generator (`kube-gen.py`), plotter, Docker Compose
environment, bats/pytest test suites. See `git log v0.1`.
