# k8s-sims — Reproducibility Report (Phase 1)

**Author of the verification:** GCDA (survey + benchmark on Kubernetes simulation tools)
**Toolkit under test:** `k8s-sims` (M. Medina, TFG UdL 2025) — image `thesmuks/k8s-sims:latest`
**Date:** 2026-06-14
**Branch:** `repro-and-new-sims`
**Verdict:** **The benchmark is reproducible** — all 5 published simulators run end-to-end and the
headline trends from `summaries/summary.json` hold — **but only after one functional fix (kubemark)
and with several determinism caveats documented below.** Nothing below is assumed: every claim is
backed by the real command output captured during this run.

---

## 1. Bottom line

| Question | Answer |
|---|---|
| Do all 5 simulators run end-to-end? | **Yes** — kwok, opensim, kube-sched, simkube, kubemark (kubemark only after the fix in §4.1). |
| Do the trends of `summary.json` reproduce? | **Yes** — kwok/opensim are the lightest, kubemark/simkube the heaviest (§3). |
| Are the absolute numbers reproducible? | **No, nor should they be** — different host (28 vCPU / 15.5 GB vs 40-core / 128 GB) and we ran `test`/`small`, not `big`. Trends only. |
| Is `docker compose up` deterministic as published? | **Partially** — see §4.2 (unpinned kube-prometheus), §4.3 (image ≠ repo HEAD), §4.4 (CRLF). |
| Did anything fail silently? | **Yes — kubemark** produced a "successful" run with **every pod unscheduled** before the fix (§4.1). |

---

## 2. Environment actually used (verified)

This is **not** the documented reference host (Alpine, 2× Xeon Silver 4210R, 128 GB). It is a
Windows laptop driving Docker Desktop's WSL2 Linux VM. The point was to find out whether the toolkit
runs at all off the original Linux box.

**Host**
- Windows 11 Pro 26200, Docker Desktop, client Docker 27.3.1 / Compose v2.29.7.
- The toolkit's hard requirement is **cgroups v2 + privileged + host cgroup access**. On Windows the
  Docker engine runs inside the WSL2 VM, which *does* provide cgroup v2:
  - `docker info` → `Cgroup Version: 2`, `Kernel 6.18.33.1-microsoft-standard-WSL2`, `CPUs: 28`, `Total Memory: 15.52GiB`.
  - Probe from a `--privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw` container:
    `cgroup.controllers = cpuset cpu io memory hugetlb pids rdma`, and creating `/sys/fs/cgroup/_probe` succeeds (writable).
- **Conclusion:** the "cgroups v2" requirement is satisfiable on Windows/macOS *via Docker Desktop's
  WSL2/LinuxKit VM*; a bare-metal Linux host is **not** strictly required. The container is Docker-in-Docker (DinD).

**Image**
- `thesmuks/k8s-sims:latest` = `d64cdc223e5f`, **2.22 GB, built ~11 months ago**. Inner Docker engine 28.3.1, cgroup v2.
- Toolchain inside: kubectl v1.33.2, kind 0.29.0, kwokctl v0.7.0, skctl 2.3.1, Python 3.12.11, Go 1.24.4, libcgroup `cgcreate`.

**How the simulators were run.** `docker compose up` runs `kube-director.sh`, which iterates the
`SIM_MODULES` list and **`break`s on the first failure** (`kube-director.sh:174`). Because `opensim`
is **first** in `SIM_MODULES`, a single early failure would abort the whole batch. To get
per-simulator pass/fail granularity we instead started the image with a `sleep` entrypoint, started
the inner `dockerd`, and called `kube-run.sh -m <sim> -e <data> -n 1 -x <timeout> -o <csv>` for each,
with `CONTAINERIZED=true` (so metric collection reads `/sys/fs/cgroup/docker/<id>`).

---

## 3. Results and trend comparison

Datasets: `test` = 1 node / 1 pod (smoke); `small` = 100 nodes / **1067 pods**, single config, `-n 1`.
Reference `summary.json` is from `big` (≈thousands of pods) on the 128 GB host — preserved untouched
as `summaries/summary.matias-big.json`.

### 3.1 `small` (100 nodes, 1067 pods) — reproduced here

| Simulator | run_time (s) | total_cpu (s) | mem_peak (GB) | unscheduled / 1067 |
|---|---:|---:|---:|---:|
| **opensim** | 2 | 2 | **0.12** | 1 |
| **kwok** | 32 | 22 | **0.46** | 25 |
| **kube-sched** | 29 | 27 | **0.75** | 16 |
| **kubemark** *(after fix §4.1)* | 112 | 218 | **6.92** | 306 |
| **simkube** | 279 | 232 | **7.49** | 0 |

### 3.2 Reference `summary.json` (`big`, original host) — averages

| Simulator | total_cpu avg (s) | mem_peak avg (GB) |
|---|---:|---:|
| kwok | 193 | **1.15** |
| opensim | 260 | **2.63** |
| kube-sched | 825 | **5.01** |
| simkube | 698 | **8.69** |
| kubemark | 7439 | **15.54** |

### 3.3 Do the trends hold? **Yes.**
- **kwok and opensim are the two lightest** in *both* runs — confirms "KWOK/OpenSim = best".
- **kubemark and simkube are the two heaviest** in *both* runs — confirms "Kubemark = worst" (at scale).
- Two scale-dependent re-orderings, both explainable (not contradictions):
  - **opensim vs kwok**: on `small` opensim < kwok; on `big` opensim > kwok. opensim is a one-shot
    scheduler that finishes a small workload in ~2 s (almost no accumulation), whereas kwok keeps a
    live apiserver/etcd with a higher fixed baseline. At `big` scale opensim's per-pod work dominates.
  - **kubemark vs simkube**: on `small` kubemark(6.92) < simkube(7.49); on `big` kubemark(15.54) ≫
    simkube(8.69). kubemark's cost scales with the **number of hollow nodes** (each is a real pod
    running a fake kubelet), so it explodes from 100 → thousands of nodes; simkube is dominated by a
    roughly fixed Prometheus stack (~6 GB), so it grows more gently. This is exactly why kubemark
    becomes "the worst" only at large scale.

The full benchmark→aggregate→plot pipeline was also exercised: `min-max-avg.py` produced
`results-repro/small-final/summary.json` and `kube-plot.py` produced 13 charts
(`results-repro/small-final/plots/`).

---

## 4. Findings (reproducibility risks), with evidence and fixes

### 4.1 🔴 kubemark scheduled **nothing** — silent failure — **FIXED + verified**
On `small`, kubemark first reported a clean completion but with **unscheduled = 1067/1067** (CSV
`100|1067|0|0|96|142|88|53|6.03|1067`). Root cause confirmed from the hollow-kubelet logs:

```
Failed to contact API server when waiting for CSINode publishing:
Get "https://127.0.0.1:38725/apis/storage.k8s.io/v1/csinodes/openb-node-0000":
dial tcp 127.0.0.1:38725: connect: connection refused
"node sync has not completed yet"
```

The kubemark hollow-node pods run *inside* the kind cluster and read a kubeconfig whose
`server:` is `https://127.0.0.1:<port>` — i.e. the pod itself, not the API server. The line that
rewrites it to the in-cluster Service endpoint was **commented out** in
`modules/kubemark/module.sh`:

```sh
#sed -i 's|server: https://127.0.0.1:[0-9]\+|server: https://kubernetes.default.svc:443|' "$LOCAL_PATH/config"
```

With no fake node ever registering, **every pod stays Pending** and kubemark consumes CPU/RAM
producing meaningless scheduling results. (This is consistent with `summary.json`'s high kubemark
CPU/memory — those numbers measure *resource consumption*, not successful scheduling, and
`summary.json` does not record `unscheduled_pods`, so the defect was invisible there.)

**Fix (applied on this branch, verified):** un-comment and target `$CONFIG_PATH`. Manual proof —
after rewriting the server to `https://kubernetes.default.svc:443`, the hollow node registers:

```
NAME              STATUS   ROLES           AGE   VERSION
openb-node-0000   Ready    node            37s   v1.29.0
```

Re-running kubemark `small` with the fix: **unscheduled 1067 → 306** (761 pods now schedule), CSV
`100|1067|0|0|112|218|145|74|6.92|306`. (The residual 306 are pods that did not place within the
scheduling timeout while the 100 hollow nodes were still registering — a time-budget effect, not the
networking bug.)

### 4.2 🟠 SimKube clones `kube-prometheus` with **no pinned ref** — confirmed non-determinism
`modules/simkube/module.sh:30` → `git clone https://github.com/prometheus-operator/kube-prometheus.git`
(default branch, no tag/commit). The deployed Prometheus stack therefore drifts with upstream over
time. It worked today (simkube `small`: all 1067 pods scheduled, 7.49 GB), but the result is **not
reproducible across dates**. *Recommendation:* `git clone --branch <release> --depth 1` and pin a
commit (the rest of the module already pins `simkube@v2.3.0` and the KWOK manifests at v0.7.0).

### 4.3 🟠 Published image ≠ current repo HEAD — `docker compose up` runs **old code**
The compose file uses `image:` (pull), not `build:`. The pulled image is ~11 months old and differs
from the repo:
- SimKube driver image at runtime is `sk-driver:v2.3.1`, although the current module passes `--driver-image …sk-driver:v2.3.0`.
- `/pylib` in the image **lacks `msgpack`**, although `requirements.txt` now pins `msgpack>=1.1.0` (pytest `test_sktrace.py` needs it).
- `utils/min-max-avg.py` is **not present** in the image (`Dockerfile` only copies `kube-gen.py`, `kube-plot.py`, `sktrace.py`), so the aggregation step of the pipeline cannot run inside the published container.

*Recommendation:* for deterministic reproduction of the *current* code, build the image from the
pinned Dockerfile (`docker compose build` / tag a release) rather than pulling `:latest`; copy
`min-max-avg.py` in the Dockerfile; rebuild whenever `requirements.txt` changes.

### 4.4 🟠 CRLF line endings + no `.gitattributes` — breaks on rebuild from a Windows checkout
Every shell script in the repo is **CRLF** (`kube-run.sh`, `kube-director.sh`, `entrypoint.sh`, all
`modules/*/module.sh`, the mock shims and `*.conf`), and there is **no `.gitattributes`**. Sourced in
the Alpine container, a `\r` makes function definitions vanish (`create_cluster: command not found`)
and makes the mock shims fail (`exit: 0: numeric argument required`). The published image works only
because it was built from a normalized (LF) checkout. Anyone rebuilding from a Windows clone gets a
broken image. *Fix applied on this branch:* added `.gitattributes` forcing `eol=lf` for `*.sh`/`*.bash`/
`*.bats`/`*.conf` and treating `modules/opensim/cmd` as binary. **The only 2 bats "failures" we saw
were purely this CRLF artifact** (see §5).

### 4.5 🟡 OpenSimulator ships as a precompiled binary — provenance unverifiable
`modules/opensim/cmd` (~the Alibaba `open-simulator`/"simon" CLI) is a committed prebuilt binary; it
is never built from source and no upstream commit is pinned. It *works* (cgroup v2 created via
`cgcreate`, `Simulation success!`, EXIT=0) and is the lightest simulator, but the binary cannot be
audited or rebuilt. *Recommendation:* add a build stage that compiles open-simulator from a pinned
commit, or at least record the source commit + build flags and a checksum.

### 4.6 🟡 kwok ignores the pinned node image
The kwok module passes `--kind-node-image kindest/node:v1.29.0`, but `kwokctl` pulled
`registry.k8s.io/kube-apiserver:v1.33.0` (and matching components) — i.e. its **default** k8s
version, not the pinned 1.29. Functionally fine here, but the control-plane version is effectively
unpinned for kwok. *Recommendation:* pin via `kwokctl --kube-version v1.29.0` (binary runtime) for parity with the other modules.

### 4.7 🟡 `kube-director.sh` aborts the whole batch on the first simulator failure
`kube-director.sh:174-178` `break`s on any non-zero `kube-run.sh`, and `SIM_MODULES` lists `opensim`
first. A single fragile simulator kills the run for all others. *Recommendation:* `continue` (record
the failure) instead of `break`, or make ordering/failure policy configurable.

---

## 5. Test suites (run inside the container against the current repo, CRLF normalized)

| Suite | Result | Notes |
|---|---|---|
| bats (`tests/bash/run.sh [--with-mocks]`) | **21 / 21 pass** | The 2 initial failures (#19, #20) were CRLF in the copied mock shims/`.conf`; after LF normalization the suite is green (`pass=21 fail=0 skip=0`). Requires `curl` for first-run bats bootstrap (absent from the runtime image — install `curl`). |
| pytest (`tests/test_binpack.py`, `test_sktrace.py`, `test_e2e_validation.py`) | **36 / 36 pass** | Needs `pytest` (not in `requirements.txt`) and `msgpack` (absent from the published image's `/pylib`, §4.3). |
| `utils/validate-checkpoint.sh` | baseline / plotting / path-spaces / collision **OK** | `docs` stage needs a real `.git` (it runs `git`), so it errors in a non-git copy — not a code defect. |

---

## 6. Recommendations for deterministic reproduction (priority order)

1. **Apply the kubemark kubeconfig fix** (§4.1) — without it kubemark results are meaningless. *(done on this branch)*
2. **Add `.gitattributes` (`eol=lf`)** so rebuilds from any OS produce working scripts. *(done on this branch)*
3. **Pin `kube-prometheus`** to a tag/commit in the simkube module (§4.2).
4. **Reproduce from a built image, not `:latest`** — pin a release tag; add `min-max-avg.py` to the
   Dockerfile; add `pytest` to a dev-requirements; rebuild on `requirements.txt` changes (§4.3).
5. **Build OpenSimulator from a pinned source commit** (or record commit + checksum) (§4.5).
6. **Pin kwok's k8s version** (§4.6) and make `kube-director.sh` failure policy non-fatal (§4.7).
7. Document the **Docker Desktop / WSL2** path as a supported way to satisfy cgroup v2 on Windows/macOS (§2).

---

## 7. Artifacts produced by this verification
- `summaries/summary.matias-big.json` — byte-for-byte backup of the original reference summary.
- `results-repro/test/*.csv` — smoke results for all 5 simulators (`test` dataset).
- `results-repro/small-final/*.csv` — `small` results for all 5 simulators (kubemark = fixed run).
- `results-repro/small-final/summary.json` — aggregated via `min-max-avg.py`.
- `results-repro/small-final/plots/*.png` — 13 charts via `kube-plot.py`.
- Code changes on `repro-and-new-sims`: `modules/kubemark/module.sh` (fix), `.gitattributes` (new).

---

## Acknowledgment

This work has been granted by the Ministerio de Ciencia, Innovación y Universidades (MICIU) AEI/10.13039/501100011033 under contract PID2023-146193OB-I00.
