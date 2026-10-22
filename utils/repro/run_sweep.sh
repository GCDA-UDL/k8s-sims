#!/usr/bin/env bash
# Containerised sweep runner (KubeSBS reproduction package).
# Generalises the June-2026 unified sweep so any dataset and any set of
# simulators can be re-run with one command. Run from the repository root:
#
#   bash utils/repro/run_sweep.sh                    # benchmark: 6 simulators + vanilla, 3 runs
#   DATASET=big MODULES="opensim kwok kube-sched simkube kubemark kcs" \
#     bash utils/repro/run_sweep.sh                  # the big sweep (several hours)
#
# Variables (all optional):
#   DATASET        data/<DATASET> to run            (default: benchmark)
#   MODULES        space-separated simulators       (default: opensim kwok kube-sched simkube kubemark kcs vanilla)
#   RUNS           repetitions per configuration    (default: 3)
#   OUT            output folder                    (default: results-repro/<DATASET>-<host>-<yyyymmdd>)
#   IMAGE          runner image                     (default: thesmuks/k8s-sims:latest)
#   MEM_THRESHOLD  host memory threshold, percent   (default: 95)
#   MAX_TIME       max seconds per simulation       (default: -1, no limit)
#
# Compare the new run with the published reference afterwards, e.g.:
#   python3 utils/repro/compare_runs.py results-repro/benchmark-all "$OUT"
set -euo pipefail

DATASET="${DATASET:-benchmark}"
MODULES="${MODULES:-opensim kwok kube-sched simkube kubemark kcs vanilla}"
RUNS="${RUNS:-3}"
IMAGE="${IMAGE:-thesmuks/k8s-sims:latest}"
MEM_THRESHOLD="${MEM_THRESHOLD:-95}"
MAX_TIME="${MAX_TIME:--1}"
OUT="${OUT:-results-repro/${DATASET}-$(hostname -s)-$(date +%Y%m%d)}"

[[ -f kube-director.sh ]] || { echo "Run this from the repository root."; exit 1; }
[[ -d "data/${DATASET}" ]] || { echo "Dataset not found: data/${DATASET}"; exit 1; }

mkdir -p "$OUT"
OUT_ABS="$(cd "$OUT" && pwd)"

if [[ " $MODULES " == *" kcs "* && ! -f modules/kcs/kcs-yamlsim ]]; then
  echo "==> Building kcs-yamlsim (static linux/amd64)"
  docker run --rm -v "$PWD":/work -w /work -e CGO_ENABLED=0 golang:1.24-alpine \
    sh -c "apk add --no-cache git bash >/dev/null && bash modules/kcs/build.sh"
  [[ -f modules/kcs/kcs-yamlsim ]] || { echo "kcs build failed"; exit 1; }
fi

# The module list and the run provenance live next to the results.
printf '%s\n' $MODULES > "$OUT_ABS/SIM_MODULES"
{
  echo "date=$(date -Iseconds)"
  echo "host=$(hostname)"
  echo "commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "image=${IMAGE}"
  docker image inspect --format 'image_id={{.Id}}' "$IMAGE" 2>/dev/null || echo "image_id=unknown"
  echo "dataset=${DATASET}"
  echo "modules=$(paste -sd' ' "$OUT_ABS/SIM_MODULES")"
  echo "runs=${RUNS}"
  echo "cpus=$(nproc)"
  echo "mem_kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
} > "$OUT_ABS/RUN_INFO"
cat "$OUT_ABS/RUN_INFO"

kcs_mount=()
if [[ -f modules/kcs/kcs-yamlsim ]]; then
  kcs_mount=(-v "$PWD/modules/kcs/kcs-yamlsim":/usr/local/bin/kcs-yamlsim:ro)
fi

docker run --rm --privileged --cgroupns host \
  -e CONTAINERIZED=true \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  -v "$PWD/data":/data:ro \
  -v "$PWD/modules":/modules:rw \
  -v "$PWD/kube-director.sh":/kube-director.sh:ro \
  -v "$PWD/kube-run.sh":/kube-run.sh:ro \
  -v "$PWD/utils":/utils:rw \
  -v "$OUT_ABS/SIM_MODULES":/SIM_MODULES:ro \
  "${kcs_mount[@]}" \
  -v "$OUT_ABS":/results \
  "$IMAGE" \
  -e "/data/${DATASET}" -n "$RUNS" -s 0 -o /results -t "$MEM_THRESHOLD" -x "$MAX_TIME"

echo "==> Done. Results in $OUT:"
ls -la "$OUT"
