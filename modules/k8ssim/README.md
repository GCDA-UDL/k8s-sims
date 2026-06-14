# K8sSim (Volcano) module

K8sSim ([LINC-BIT/k8sSimulator](https://github.com/LINC-BIT/k8sSimulator)) is the
only simulator integrated here that exercises the **Volcano** scheduler — gang
scheduling, DRF, SLA, and the LRP / MRP / BRA / BINPACK plugins for AI/GPU
workloads. The five built-in simulators (kwok, opensim, kube-sched, simkube,
kubemark) only cover the default kube-scheduler, so K8sSim closes that gap.

> The TFG noted K8sSim as *"not available"*. **That is incorrect** — the repo is
> public and the Volcano simulator builds and runs (verified, see below).

## What is integrated

The upstream repo ships two halves:

| Part | State in repo | Integrated? |
|---|---|---|
| `Volcano Simulation/Volcano_simulator` (Go, `cmd/sim`, **vendored**) | full source + `vendor/` | **Yes** — this is the buildable, reproducible Volcano simulator. |
| `Kubernetes Simulation/k8s-simulator-prop` (generic kube-scheduler sim) | **only `.idea/` IDE files — no Go source** | No (source not published; functionally overlaps the existing `kube-sched` module anyway). |

So this module integrates the **Volcano** simulator, which is both the unique
value and the only part actually shipped as source.

## Reproducible build (pinned)

- Upstream: `https://github.com/LINC-BIT/k8sSimulator`
- **Pinned commit: `7168cb3281e98d72dce11c723fced1eb9eda950a`** (2023-02-09)
- Module: `volcano.sh/volcano` · Go directive `go 1.17` · deps **vendored** (no network needed to build)

```sh
git clone https://github.com/LINC-BIT/k8sSimulator.git
cd k8sSimulator
git checkout 7168cb3281e98d72dce11c723fced1eb9eda950a
cd "Volcano Simulation/Volcano_simulator"
CGO_ENABLED=0 go build -mod=vendor -o k8ssim-vol ./cmd/sim
```

Verified build: Go 1.24.4, ~13 s, 58 MB static binary. The binary is **not**
committed (size + the toolkit's own guidance to build from source rather than
ship prebuilt binaries — see `REPRODUCIBILITY_REPORT.md` §4.5). Put the binary
where the module can find it (in order):

1. `$K8SSIM_BIN` (explicit path)
2. `modules/k8ssim/k8ssim-vol`
3. `/usr/local/bin/k8ssim-vol`
4. `/tmp/k8ssim-vol`

Dockerfile builder stanza (recommended) to bake it into the image:

```dockerfile
RUN git clone https://github.com/LINC-BIT/k8sSimulator.git /tmp/k8ssim && \
    cd /tmp/k8ssim && git checkout 7168cb3281e98d72dce11c723fced1eb9eda950a && \
    cd "Volcano Simulation/Volcano_simulator" && \
    CGO_ENABLED=0 go build -mod=vendor -o /usr/local/bin/k8ssim-vol ./cmd/sim
```

## How it runs

The simulator is a single Go process serving an HTTP API on **`:8006`**
(hardcoded in `cmd/sim/main.go`). Resource accounting follows the `opensim`
model: the server runs inside a dedicated cgroup (`/sys/fs/cgroup/k8ssim`) and
`kube-run.sh`'s `metric_collector` reads that cgroup's `cpu.stat` /
`memory.current` (cgroup v2). One fresh server is started per run because
`/reset` refuses while a job is still running.

`k8ssim_driver.py` (Python **stdlib only** — replaces the bundled `SimRun.py`,
which needs requests/munch/prettytable/matplotlib/MySQL) speaks the protocol:

```
POST /reset      {"period":"-1","nodes":<yaml>,"workload":<yaml>}
POST /step       {"conf":<scheduler-conf>}
POST /stepResult {"none":""}        # "0" while running; full JSON when done
POST /stepResultAnyway {"none":""}  # fallback: partial state, never blocks
```

It prints `Unscheduled: <n>` (the convention `kube-run.sh` greps) and never
hangs: if a workload can't complete within `--max-wait` it falls back to
`/stepResultAnyway` and reports the partial placement.

## Dataset format

K8sSim uses its **own** formats (not the Alibaba-derived pod manifests the other
modules use), so each data point is a pair under `data/<size>/k8ssim/`:

- `nodes-<N>.yaml` — a `cluster:` list (custom node format with `calculationSpeed`,
  `ctnCreationTime`, GPU resources under `nvidia.com/gpu`, …).
- `workload-<N>.yaml` — a `jobs:` list of Volcano `batch.volcano.sh/v1alpha1` Jobs.

⚠️ Workloads request `nvidia.com/gpu`, so the node set **must** declare GPU
capacity or every job is unschedulable. The bundled samples here come from the
upstream repo (`nodes_7-0` family + AI workloads), which are GPU-capable and tiny
(5 nodes) — enough to validate integration. Generating large, Alibaba-derived
Volcano datasets via `utils/kube-gen.py` (a `--k8ssim`/Volcano emitter) is the
documented next step; the node + Volcano-Job transformation is non-trivial.

## Usage

```sh
# default scheduler is GANG_LRP; override with K8SSIM_SCHED
./kube-run.sh -m k8ssim -e ./data/small/k8ssim -n 1 -o ./results/k8ssim.csv
K8SSIM_SCHED=SLA_BINPACK ./kube-run.sh -m k8ssim -e ./data/small/k8ssim -o ./results/k8ssim-sla.csv
```

Available `K8SSIM_SCHED` values = file stems in `scheduler_conf/`:
`GANG_LRP`, `GANG_MRP`, `GANG_BRA`, `DRF_LRP`, `DRF_MRP`, `DRF_BRA`,
`SLA_LRP`, `SLA_MRP`, `SLA_BRA`, `*_BINPACK`, `GANG_DRF_*`, `Default`.

Not added to the default `SIM_MODULES` runtime list on purpose: it needs the
binary built and uses its own dataset format, and `kube-director.sh` aborts the
whole batch on the first failing module. Run it standalone as above, or add
`k8ssim` to a custom `SIM_MODULES` once the binary and `data/<size>/k8ssim/` are
in place.

## Verified results (this integration)

Container = `thesmuks/k8s-sims` image + Docker-Desktop/WSL2 (cgroup v2).

| Dataset | Scheduler | Tasks | Scheduled | Unscheduled | run_time | mem_peak |
|---|---|---:|---:|---:|---:|---:|
| test (5 nodes) | GANG_LRP | 8 | 8 | 0 | 4 s | 0.01 GB |
| small (5 nodes) | GANG_LRP | 11 | 11 | 0 | 2 s | 0.01 GB |
| small (5 nodes) | SLA_BINPACK | 11 | 11 | 0 | 2 s | 0.01 GB |

Metrics are small because K8sSim is a pure scheduling simulator (like opensim)
and the bundled samples are tiny; the value demonstrated here is **functional
Volcano coverage**, not scale.
