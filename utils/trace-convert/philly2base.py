#!/usr/bin/env python3
"""Convert the Microsoft Philly DNN-training GPU-cluster trace
(`msr-fiddle/philly-traces`, the `cluster_job_log` JSON) into the k8s-sims base
manifest format: nodes-<N>.yaml + pods-<N>.yaml.

Philly is a *GPU* trace: each training job requests a number of GPUs, so each job
becomes a Pod that requests `nvidia.com/gpu` (plus proportional cpu/memory), and a
homogeneous GPU node pool is synthesised large enough to host the requested GPUs.
Output drops into the toolkit's data layout and is consumed by every simulator and
by kube-gen.py unchanged --- and it exercises GPU scheduling, unlike the CPU-only
Borg/Azure converters.

cluster_job_log schema (JSON array of jobs, see the philly-traces README):
  {"jobid", "user", "vc", "status": "Pass|Failed|Killed", "submitted_time",
   "attempts": [{"start_time", "end_time",
                 "detail": [{"ip", "status", "gpus": ["gpu0", ...]}]}]}
GPUs requested = number of gpu ids across the first attempt's `detail` (>=1).

NOTE: the real cluster_job_log is a single large JSON file; it is loaded into
memory (json.load) and then capped by --max-pods, matching the other converters'
simplicity. For very large logs, slice the JSON beforehand.

Usage:
  philly2base.py --joblog cluster_job_log -o out/ [--max-pods M] [--max-nodes N]
                 [--gpus-per-node 8] [--node-cpu 96] [--node-mem 512]
                 [--cpu-per-gpu 6] [--mem-per-gpu 32]
"""
import argparse
import json
import math
import os
import yaml


def _job_gpus(job):
    """GPU ids requested by a job = count across the first attempt's detail."""
    attempts = job.get("attempts") or []
    if not attempts:
        return 0
    total = 0
    for d in attempts[0].get("detail") or []:
        total += len(d.get("gpus") or [])
    return total


def load_jobs(path, max_pods, cpu_per_gpu, mem_per_gpu):
    with open(path) as fh:
        jobs = json.load(fh)
    pods = []
    for job in jobs:
        if "submitted_time" not in job:           # SUBMIT events only
            continue
        gpus = max(1, _job_gpus(job))              # default to 1 GPU if unrecorded
        cores = max(1, gpus * cpu_per_gpu)
        mem_gi = max(1, gpus * mem_per_gpu)
        pods.append({
            "apiVersion": "v1", "kind": "Pod",
            "metadata": {"name": f"philly-pod-{len(pods):05d}", "namespace": "paib-gpu"},
            "spec": {
                "containers": [{
                    "image": "philly-job:latest", "imagePullPolicy": "Always", "name": "main",
                    "resources": {
                        "limits":   {"cpu": f"{cores*1000}m", "memory": f"{mem_gi*1024}Mi", "nvidia.com/gpu": str(gpus)},
                        "requests": {"cpu": f"{cores*1000}m", "memory": f"{mem_gi*1024}Mi", "nvidia.com/gpu": str(gpus)},
                    },
                }],
                "dnsPolicy": "Default", "restartPolicy": "OnFailure",
            },
        })
        if max_pods and len(pods) >= max_pods:
            break
    return pods


def synth_nodes(pods, gpus_per_node, node_cpu, node_mem, max_nodes):
    # Size the GPU pool to hold the total requested GPUs (and cpu/memory).
    tot_gpu = sum(int(p["spec"]["containers"][0]["resources"]["requests"]["nvidia.com/gpu"]) for p in pods)
    tot_cpu = sum(int(p["spec"]["containers"][0]["resources"]["requests"]["cpu"][:-1]) / 1000 for p in pods)
    tot_mem = sum(int(p["spec"]["containers"][0]["resources"]["requests"]["memory"][:-2]) / 1024 for p in pods)
    n = max(1,
            math.ceil(tot_gpu / gpus_per_node) if gpus_per_node else 1,
            math.ceil(tot_cpu / node_cpu) if node_cpu else 1,
            math.ceil(tot_mem / node_mem) if node_mem else 1)
    if max_nodes:
        n = min(n, max_nodes)
    nodes = []
    for i in range(n):
        nodes.append({
            "apiVersion": "v1", "kind": "Node",
            "metadata": {"name": f"philly-node-{i:04d}",
                         "labels": {"beta.kubernetes.io/os": "linux", "trace": "philly",
                                    "accelerator": "nvidia-gpu"}},
            "status": {
                "allocatable": {"cpu": f"{node_cpu*1000}m", "memory": f"{node_mem*1024}Mi",
                                "nvidia.com/gpu": str(gpus_per_node), "pods": "1001"},
                "capacity":    {"cpu": f"{node_cpu*1000}m", "memory": f"{node_mem*1024}Mi",
                                "nvidia.com/gpu": str(gpus_per_node), "pods": "1001"},
            },
        })
    return nodes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--joblog", required=True, help="Philly cluster_job_log JSON")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--max-pods", type=int, default=0)
    ap.add_argument("--max-nodes", type=int, default=0, help="cap synthesised nodes (0 = auto)")
    ap.add_argument("--gpus-per-node", type=int, default=8, help="GPUs per synthesised node")
    ap.add_argument("--node-cpu", type=int, default=96, help="cores per synthesised node")
    ap.add_argument("--node-mem", type=int, default=512, help="GiB per synthesised node")
    ap.add_argument("--cpu-per-gpu", type=int, default=6, help="cores requested per GPU")
    ap.add_argument("--mem-per-gpu", type=int, default=32, help="GiB requested per GPU")
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)
    pods = load_jobs(args.joblog, args.max_pods, args.cpu_per_gpu, args.mem_per_gpu)
    if not pods:
        raise SystemExit("error: no jobs parsed; check the cluster_job_log schema")
    nodes = synth_nodes(pods, args.gpus_per_node, args.node_cpu, args.node_mem, args.max_nodes)

    n = len(nodes)
    tot_gpu = sum(int(p["spec"]["containers"][0]["resources"]["requests"]["nvidia.com/gpu"]) for p in pods)
    with open(os.path.join(args.output, f"nodes-{n}.yaml"), "w") as fh:
        yaml.dump_all(nodes, fh, default_flow_style=False)
    with open(os.path.join(args.output, f"pods-{n}.yaml"), "w") as fh:
        yaml.dump_all(pods, fh, default_flow_style=False)
    print(f"philly: {n} synthesised GPU nodes, {len(pods)} pods, {tot_gpu} GPUs requested "
          f"-> {args.output}/{{nodes,pods}}-{n}.yaml")


if __name__ == "__main__":
    main()
