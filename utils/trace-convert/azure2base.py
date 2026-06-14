#!/usr/bin/env python3
"""Convert an Azure Public Dataset VM trace (AzurePublicDatasetV2 `vmtable.csv`)
into the k8s-sims base manifest format: nodes-<N>.yaml + pods-<N>.yaml.

The Azure VM trace describes *VMs*, not cluster nodes, so each VM becomes a Pod
(requesting its core-count and memory bucket) and a homogeneous node pool is
synthesised large enough to host them. Output drops into the toolkit's data
layout and is consumed by every simulator and by kube-gen.py.

vmtable.csv columns (headerless, AzurePublicDatasetV2):
  vm_id, subscription_id, deployment_id, created, deleted, max_cpu, avg_cpu,
  p95_max_cpu, category, core_bucket, memory_bucket(GB)
Buckets may be plain numbers or ">N" strings; we take the numeric part.

Usage:
  azure2base.py --vmtable vmtable.csv -o out/ [--max-pods M]
                [--node-cpu 64] [--node-mem 256]
"""
import argparse
import csv
import math
import os
import re
import yaml


def _num(x, default=1.0):
    if x is None:
        return default
    m = re.search(r"[0-9]+(\.[0-9]+)?", str(x))
    return float(m.group()) if m else default


def load_vms(path, max_pods):
    pods = []
    with open(path, newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 11:
                continue
            cores = max(1, round(_num(row[9], 1)))       # core-count bucket
            mem_gi = max(1, round(_num(row[10], 1)))     # memory bucket (GB)
            pods.append({
                "apiVersion": "v1", "kind": "Pod",
                "metadata": {"name": f"azure-pod-{len(pods):05d}", "namespace": "paib-gpu"},
                "spec": {
                    "containers": [{
                        "image": "azure-vm:latest", "imagePullPolicy": "Always", "name": "main",
                        "resources": {"limits": {"cpu": f"{cores*1000}m", "memory": f"{mem_gi*1024}Mi"},
                                      "requests": {"cpu": f"{cores*1000}m", "memory": f"{mem_gi*1024}Mi"}},
                    }],
                    "dnsPolicy": "Default", "restartPolicy": "OnFailure",
                },
            })
            if max_pods and len(pods) >= max_pods:
                break
    return pods


def synth_nodes(pods, node_cpu, node_mem):
    # Size the pool to comfortably hold the total requested cores/memory.
    tot_cpu = sum(_num(p["spec"]["containers"][0]["resources"]["requests"]["cpu"]) / 1000 for p in pods)
    tot_mem = sum(_num(p["spec"]["containers"][0]["resources"]["requests"]["memory"]) / 1024 for p in pods)
    n_by_cpu = math.ceil(tot_cpu / node_cpu) if node_cpu else 1
    n_by_mem = math.ceil(tot_mem / node_mem) if node_mem else 1
    n = max(1, n_by_cpu, n_by_mem)
    nodes = []
    for i in range(n):
        nodes.append({
            "apiVersion": "v1", "kind": "Node",
            "metadata": {"name": f"azure-node-{i:04d}",
                         "labels": {"beta.kubernetes.io/os": "linux", "trace": "azure"}},
            "status": {
                "allocatable": {"cpu": f"{node_cpu*1000}m", "memory": f"{node_mem*1024}Mi", "pods": "1001"},
                "capacity":    {"cpu": f"{node_cpu*1000}m", "memory": f"{node_mem*1024}Mi", "pods": "1001"},
            },
        })
    return nodes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vmtable", required=True, help="Azure vmtable CSV")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--max-pods", type=int, default=0)
    ap.add_argument("--node-cpu", type=int, default=64, help="cores per synthesised node")
    ap.add_argument("--node-mem", type=int, default=256, help="GiB per synthesised node")
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)
    pods = load_vms(args.vmtable, args.max_pods)
    if not pods:
        raise SystemExit("error: no VMs parsed; check the vmtable schema")
    nodes = synth_nodes(pods, args.node_cpu, args.node_mem)

    n = len(nodes)
    with open(os.path.join(args.output, f"nodes-{n}.yaml"), "w") as fh:
        yaml.dump_all(nodes, fh, default_flow_style=False)
    with open(os.path.join(args.output, f"pods-{n}.yaml"), "w") as fh:
        yaml.dump_all(pods, fh, default_flow_style=False)
    print(f"azure: {n} synthesised nodes, {len(pods)} pods -> {args.output}/{{nodes,pods}}-{n}.yaml")


if __name__ == "__main__":
    main()
