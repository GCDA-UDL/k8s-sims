#!/usr/bin/env python3
"""Convert Google Borg cluster traces (ClusterData2011_2 CSV schema) into the
k8s-sims base manifest format: nodes-<N>.yaml (k8s Node) + pods-<N>.yaml (k8s Pod).

Once converted, the output drops straight into the toolkit's data layout and is
consumed by every simulator (kwok/opensim/kube-sched/kubemark/simkube/k8ssim/kcs)
and by kube-gen.py — no simulator changes needed.

Borg 2011 resources are normalised to the largest machine in [0,1]; we scale them
to concrete cores / GiB via --cpu-scale / --mem-scale (defaults model a 64-core /
256 GiB reference machine, matching the Alibaba base set's largest node).

Schemas (headerless CSV, see the ClusterData2011_2 schema doc):
  machine_events: time, machine_id, event_type, platform_id, cpus, memory
                  (event_type 0 = ADD)
  task_events:    time, missing, job_id, task_index, machine_id, event_type,
                  user, sched_class, priority, cpu_request, mem_request, disk, constraint
                  (event_type 0 = SUBMIT)

Usage:
  borg2base.py --machines machine_events.csv --tasks task_events.csv -o out/ \
               [--max-nodes N] [--max-pods M] [--cpu-scale 64] [--mem-scale 256]
"""
import argparse
import csv
import os
import yaml


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def load_machines(path, cpu_scale, mem_scale, max_nodes):
    nodes, seen = [], set()
    with open(path, newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 6 or row[2] != "0":      # ADD events only
                continue
            mid = row[1]
            if mid in seen:
                continue
            seen.add(mid)
            cores = max(1, round(_f(row[4]) * cpu_scale))
            mem_gi = max(1, round(_f(row[5]) * mem_scale))
            nodes.append({
                "apiVersion": "v1", "kind": "Node",
                "metadata": {"name": f"borg-node-{len(nodes):04d}",
                             "labels": {"beta.kubernetes.io/os": "linux",
                                        "trace": "google-borg"}},
                "status": {
                    "allocatable": {"cpu": f"{cores*1000}m", "memory": f"{mem_gi*1024}Mi", "pods": "1001"},
                    "capacity":    {"cpu": f"{cores*1000}m", "memory": f"{mem_gi*1024}Mi", "pods": "1001"},
                },
            })
            if max_nodes and len(nodes) >= max_nodes:
                break
    return nodes


def load_tasks(path, cpu_scale, mem_scale, max_pods):
    pods, seen = [], set()
    with open(path, newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 11 or row[5] != "0":     # SUBMIT events only
                continue
            key = (row[2], row[3])                  # (job_id, task_index)
            if key in seen:
                continue
            seen.add(key)
            milli = max(10, round(_f(row[9]) * cpu_scale * 1000))
            mem_mi = max(16, round(_f(row[10]) * mem_scale * 1024))
            pods.append({
                "apiVersion": "v1", "kind": "Pod",
                "metadata": {"name": f"borg-pod-{len(pods):05d}", "namespace": "paib-gpu"},
                "spec": {
                    "containers": [{
                        "image": "borg-task:latest", "imagePullPolicy": "Always", "name": "main",
                        "resources": {"limits": {"cpu": f"{milli}m", "memory": f"{mem_mi}Mi"},
                                      "requests": {"cpu": f"{milli}m", "memory": f"{mem_mi}Mi"}},
                    }],
                    "dnsPolicy": "Default", "restartPolicy": "OnFailure",
                },
            })
            if max_pods and len(pods) >= max_pods:
                break
    return pods


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--machines", required=True, help="machine_events CSV")
    ap.add_argument("--tasks", required=True, help="task_events CSV")
    ap.add_argument("-o", "--output", required=True, help="output directory")
    ap.add_argument("--max-nodes", type=int, default=0)
    ap.add_argument("--max-pods", type=int, default=0)
    ap.add_argument("--cpu-scale", type=float, default=64.0, help="cores at normalised cpu=1.0")
    ap.add_argument("--mem-scale", type=float, default=256.0, help="GiB at normalised memory=1.0")
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)
    nodes = load_machines(args.machines, args.cpu_scale, args.mem_scale, args.max_nodes)
    pods = load_tasks(args.tasks, args.cpu_scale, args.mem_scale, args.max_pods)
    if not nodes or not pods:
        raise SystemExit("error: no ADD machines or SUBMIT tasks parsed; check the trace schema")

    n = len(nodes)
    with open(os.path.join(args.output, f"nodes-{n}.yaml"), "w") as fh:
        yaml.dump_all(nodes, fh, default_flow_style=False)
    with open(os.path.join(args.output, f"pods-{n}.yaml"), "w") as fh:
        yaml.dump_all(pods, fh, default_flow_style=False)
    print(f"google-borg: {n} nodes, {len(pods)} pods -> {args.output}/{{nodes,pods}}-{n}.yaml")


if __name__ == "__main__":
    main()
