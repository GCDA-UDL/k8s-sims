#!/usr/bin/env bash
# Download the public cluster traces k8s-sims supports (Alibaba / Google Borg /
# Azure) into a drop-in layout for the converters in this directory.
#
# RUN THIS ON THE EXPERIMENT SERVER, NOT on a OneDrive/Dropbox-synced folder:
# the full traces are large (Borg task_events tens of GB, Azure vmtable ~GB).
# Pick a TARGET on local/scratch disk.
#
# Layout produced (TARGET defaults to ./traces):
#   TARGET/borg/machine_events.csv      -> borg2base.py --machines
#   TARGET/borg/task_events.csv         -> borg2base.py --tasks
#   TARGET/azure/vmtable.csv            -> azure2base.py --vmtable
#   TARGET/alibaba/clusterdata/...      -> cluster-trace-gpu-v2023 (full GPU trace)
#
# Usage:
#   ./download_traces.sh --all                 # everything, into ./traces
#   ./download_traces.sh --borg --azure -o /data/traces
#   ./download_traces.sh --azure               # just one source
#
# Tools: bash, curl, gunzip, git; gsutil for Borg (pip install gsutil).
set -euo pipefail

TARGET="./traces"
DO_ALIBABA=0; DO_BORG=0; DO_AZURE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --all)     DO_ALIBABA=1; DO_BORG=1; DO_AZURE=1 ;;
    --alibaba) DO_ALIBABA=1 ;;
    --borg)    DO_BORG=1 ;;
    --azure)   DO_AZURE=1 ;;
    -o|--out)  TARGET="$2"; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done
[ $((DO_ALIBABA+DO_BORG+DO_AZURE)) -eq 0 ] && { echo "nothing selected; use --all or --alibaba/--borg/--azure"; exit 2; }

need() { command -v "$1" >/dev/null 2>&1 || { echo "MISSING TOOL: $1 ($2)"; return 1; }; }
mkdir -p "$TARGET"
echo "== target: $TARGET =="

# ---- Google Borg (ClusterData2011_2, public GCS bucket) --------------------
if [ "$DO_BORG" = 1 ]; then
  echo "== Borg (gs://clusterdata-2011-2) =="
  if need gsutil "pip install gsutil"; then
    mkdir -p "$TARGET/borg/raw"
    gsutil -m cp -r gs://clusterdata-2011-2/machine_events "$TARGET/borg/raw/"
    gsutil -m cp -r gs://clusterdata-2011-2/task_events    "$TARGET/borg/raw/"
    # 2011 parts are headerless gzipped CSV; concat into the single files the converter expects
    zcat "$TARGET"/borg/raw/machine_events/part-*.csv.gz > "$TARGET/borg/machine_events.csv"
    zcat "$TARGET"/borg/raw/task_events/part-*.csv.gz     > "$TARGET/borg/task_events.csv"
    echo "  -> $TARGET/borg/{machine_events,task_events}.csv"
  else
    echo "  SKIPPED Borg (install gsutil first: pip install gsutil)"
  fi
fi

# ---- Azure (AzurePublicDatasetV2 vmtable) ----------------------------------
if [ "$DO_AZURE" = 1 ]; then
  echo "== Azure (AzurePublicDatasetV2 vmtable) =="
  if need curl "curl package" && need gunzip "gzip package"; then
    mkdir -p "$TARGET/azure"
    URL="https://github.com/Azure/AzurePublicDataset/releases/download/dataset-v2/trace_data_vmtable_vmtable.csv.gz"
    curl -fL -C - -o "$TARGET/azure/vmtable.csv.gz" "$URL"
    gunzip -kf "$TARGET/azure/vmtable.csv.gz"
    echo "  -> $TARGET/azure/vmtable.csv"
  else
    echo "  SKIPPED Azure"
  fi
fi

# ---- Alibaba (cluster-trace-gpu-v2023) -------------------------------------
if [ "$DO_ALIBABA" = 1 ]; then
  echo "== Alibaba (cluster-trace-gpu-v2023) =="
  if need git "git package"; then
    mkdir -p "$TARGET/alibaba"
    if [ -d "$TARGET/alibaba/clusterdata/.git" ]; then
      git -C "$TARGET/alibaba/clusterdata" pull --ff-only || true
    else
      git clone --depth 1 https://github.com/alibaba/clusterdata "$TARGET/alibaba/clusterdata"
    fi
    echo "  -> GPU 2023 trace under $TARGET/alibaba/clusterdata/cluster-trace-gpu-v2023/"
    echo "     NOTE: k8s-sims already ships the derived base in utils/base/{nodes,pods}.yaml;"
    echo "     use the full trace only if you need bigger/raw Alibaba inputs (see that subdir's README)."
  else
    echo "  SKIPPED Alibaba"
  fi
fi

cat <<EOF

== done. Next: convert to toolkit datasets ==
  # Borg  -> data/borg
  python "$(dirname "$0")/borg2base.py" \\
      --machines "$TARGET/borg/machine_events.csv" --tasks "$TARGET/borg/task_events.csv" \\
      -o data/borg --max-nodes 100 --max-pods 1000
  # Azure -> data/azure
  python "$(dirname "$0")/azure2base.py" \\
      --vmtable "$TARGET/azure/vmtable.csv" -o data/azure --max-pods 1000 --node-cpu 64 --node-mem 256
  # Alibaba is the built-in default of kube-gen.py (utils/base); no convert step needed.

Then run a sim, e.g.:  ./kube-run.sh -m kcs -e data/borg -o results/kcs-borg.csv
EOF
