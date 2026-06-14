#!/usr/bin/env python3
"""Minimal, dependency-free driver for the K8sSim Volcano simulator.

The bundled SimRun.py pulls in requests/munch/prettytable/matplotlib/MySQL and a
`figures` package, none of which are needed to run a simulation and collect the
scheduling outcome. This driver speaks the same HTTP protocol using only the
Python standard library so it can run inside the k8s-sims Alpine container.

Protocol (server hardcodes :8006, see cmd/sim/main.go):
  POST /reset      {"period": "-1", "nodes": <yaml>, "workload": <yaml>}
  POST /step       {"conf": <scheduler-conf yaml>}
  POST /stepResult {"none": ""}   -> returns "0" while running, full JSON when done

It prints one line `Unscheduled: <n>` (same convention kube-run.sh/opensim greps)
plus a short summary, and exits 0 on success.
"""
import argparse
import json
import sys
import time
import urllib.request


def _post(base, path, payload, timeout=30):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base + path, data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body.strip()


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def main():
    ap = argparse.ArgumentParser(description="Drive the K8sSim Volcano simulator.")
    ap.add_argument("--server", default="http://localhost:8006")
    ap.add_argument("--nodes", required=True, help="cluster/nodes YAML file")
    ap.add_argument("--workload", required=True, help="Volcano jobs YAML file")
    ap.add_argument("--conf", required=True, help="scheduler_conf_sim YAML file")
    ap.add_argument("--period", default="-1")
    ap.add_argument("--poll-interval", type=float, default=0.2)
    ap.add_argument("--max-wait", type=float, default=600.0,
                    help="if no clean final result after this many seconds, fall "
                         "back to /stepResultAnyway and report partial scheduling")
    args = ap.parse_args()

    nodes = _read(args.nodes)
    workload = _read(args.workload)
    conf = _read(args.conf)

    reset = _post(args.server, "/reset",
                  {"period": str(args.period), "nodes": nodes, "workload": workload})
    if str(reset) == "0":
        print("ERROR: reset rejected (a job is still running); restart the server",
              file=sys.stderr)
        return 2
    print("---Simulation Reset---")

    _post(args.server, "/step", {"conf": conf})
    print("---Simulation Step submitted---")

    deadline = time.time() + args.max_wait
    result = "0"
    completed = False
    while time.time() < deadline:
        result = _post(args.server, "/stepResult", {"none": ""})
        if str(result) != "0":
            completed = True
            break
        time.sleep(args.poll_interval)

    if not completed:
        # The workload could not run to completion within --max-wait (e.g. some
        # jobs are unschedulable). Pull the current cluster state so we can still
        # report how many tasks were placed instead of hanging the harness.
        print("WARN: no clean completion within --max-wait; using /stepResultAnyway",
              file=sys.stderr)
        result = _post(args.server, "/stepResultAnyway", {"none": ""})

    jobs = result.get("Jobs", {}) if isinstance(result, dict) else {}
    total_tasks = 0
    scheduled_tasks = 0
    completed_jobs = 0
    for _job_name, job in jobs.items():
        tasks = (job or {}).get("Tasks", {}) or {}
        job_all_ok = bool(tasks)
        for _task_name, task in tasks.items():
            total_tasks += 1
            node = (task or {}).get("NodeName", "")
            phase = (((task or {}).get("Pod") or {}).get("status") or {}).get("phase", "")
            if node:
                scheduled_tasks += 1
            if phase != "Succeeded":
                job_all_ok = False
        if job_all_ok:
            completed_jobs += 1

    unscheduled = total_tasks - scheduled_tasks
    print("Completed: {}  Jobs: {} ({} done)  Tasks: {}  Scheduled: {}".format(
        completed, len(jobs), completed_jobs, total_tasks, scheduled_tasks))
    print("Unscheduled: {}".format(unscheduled))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
