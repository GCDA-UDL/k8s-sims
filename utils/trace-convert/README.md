# Trace converters — Google Borg & Azure → k8s-sims datasets

The toolkit was built around Alibaba traces (`utils/base/{nodes,pods}.yaml`).
These converters add two more public workload sources by emitting the **same**
manifest format, so every simulator (kwok, opensim, kube-sched, kubemark,
simkube, k8ssim, kcs) and `kube-gen.py` consume them unchanged — no per-sim work.

Each converter writes `nodes-<N>.yaml` + `pods-<N>.yaml` (sharing the same `<N>`,
as `kube-run.sh` pairs them by the number in the node filename), so the output is
a drop-in toolkit dataset directory.

## Google Borg — `borg2base.py`

- Source: [`google/cluster-data`](https://github.com/google/cluster-data) (ClusterData2011_2; the 2019 set has an analogous schema).
- Maps `machine_events` ADD rows → k8s Nodes, `task_events` SUBMIT rows → k8s Pods.
- Borg resources are normalised to [0,1] (largest machine = 1.0); `--cpu-scale` /
  `--mem-scale` scale them to concrete cores / GiB (defaults 64 / 256).
- Borg 2011 has no GPU, so the manifests are CPU/memory only.

```sh
python utils/trace-convert/borg2base.py \
    --machines machine_events.csv --tasks task_events.csv -o data/borg-small \
    --max-nodes 100 --max-pods 1000
./kube-run.sh -m kcs -e data/borg-small -o results/kcs-borg.csv
```

## Azure — `azure2base.py`

- Source: [`Azure/AzurePublicDataset`](https://github.com/Azure/AzurePublicDataset) (AzurePublicDatasetV2 `vmtable.csv`).
- Each VM → a Pod (core-count + memory bucket). The trace has no cluster nodes,
  so a homogeneous node pool (`--node-cpu` / `--node-mem`, default 64/256 GiB) is
  synthesised large enough to host the VMs.

```sh
python utils/trace-convert/azure2base.py \
    --vmtable vmtable.csv -o data/azure-small --max-pods 1000 --node-cpu 64 --node-mem 256
./kube-run.sh -m kcs -e data/azure-small -o results/kcs-azure.csv
```

## Getting the real traces

The public repos are mostly documentation + download scripts; the data lives on
GCS / Azure Blob and is large (Borg 2019 is TB-scale, Azure VM trace is GB-scale).
Download per the upstream instructions, then point the converters at the CSVs.
`samples/` holds tiny synthetic CSVs **in the documented schemas** for testing the
converters offline.

## Verified (synthetic samples → kcs)

| Source | sample in | converted | kcs run |
|---|---|---|---|
| Google Borg | 5 machines / 12 tasks | nodes-5 + pods-5 (12 pods) | 0 unscheduled |
| Azure | 8 VMs | nodes-3 (synth) + pods-3 (8 pods) | 0 unscheduled |

Both validated end-to-end: `samples/*.csv` → converter → toolkit dataset → a real
simulator run. Full-trace runs only need the user to drop in the downloaded CSVs.
