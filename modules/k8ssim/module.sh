#!/bin/bash
# K8sSim (LINC-BIT) — Volcano scheduling simulator module.
#
# K8sSim is the only simulator in this toolkit that exercises the *Volcano*
# scheduler (gang/DRF/SLA scheduling with the LRP/MRP/BRA/BINPACK plugins) — the
# five built-in simulators only cover the default kube-scheduler. The simulator
# is a single Go process (a fork of volcano.sh/volcano, package cmd/sim) that
# serves an HTTP API on :8006; a Python driver feeds it a node set + a Volcano
# job workload + a scheduler configuration and polls for the scheduling result.
#
# Resource accounting follows the same model as the `opensim` module: the
# simulator runs inside a dedicated cgroup and `metric_collector` reads that
# cgroup's cpu.stat / memory.current (cgroup v2). One fresh server is started
# per run so the simulator state is always clean (/reset refuses while a job is
# still running).
#
# Reproducible build (pinned): see modules/k8ssim/README.md. The module expects
# a prebuilt binary; point K8SSIM_BIN at it (default search path below).

readonly LOCAL_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly CGROUP_NAME="k8ssim"
readonly K8SSIM_PORT="${K8SSIM_PORT:-8006}"
readonly K8SSIM_SERVER="http://localhost:${K8SSIM_PORT}"

# Scheduler algorithm: one of the files in modules/k8ssim/scheduler_conf/*.yaml
# (GANG_LRP, GANG_MRP, GANG_BRA, DRF_*, SLA_*, *_BINPACK, Default). Override with
# K8SSIM_SCHED. This selects which Volcano scheduling policy is simulated.
readonly K8SSIM_SCHED="${K8SSIM_SCHED:-GANG_LRP}"
readonly K8SSIM_CONF="${LOCAL_PATH}/scheduler_conf/${K8SSIM_SCHED}.yaml"

# Workload file pattern. K8sSim consumes Volcano Jobs, not plain pods, so the
# workload lives next to the node file as workload-<N>.yaml (falls back to the
# generic pods-<N>.yaml slot that kube-run.sh computes).
FILE_PATTERN="nodes-*.yaml"

# Locate the simulator binary (built from the pinned commit, see README).
resolve_binary(){
    if [[ -n "${K8SSIM_BIN:-}" && -x "${K8SSIM_BIN}" ]]; then
        echo "${K8SSIM_BIN}"; return 0
    fi
    for cand in "${LOCAL_PATH}/k8ssim-vol" "/usr/local/bin/k8ssim-vol" "/tmp/k8ssim-vol"; do
        [[ -x "$cand" ]] && { echo "$cand"; return 0; }
    done
    return 1
}

K8SSIM_PID=-1

metric_collector(){
    local TYPE="$1"
    if [[ "$TYPE" == "cpu" ]]; then
        get_cpu_usage "false" "$CGROUP_NAME"
    elif [[ "$TYPE" == "memory" ]]; then
        get_memory_usage "false" "$CGROUP_NAME"
    fi
}

create_cluster(){
    local BIN
    if ! BIN="$(resolve_binary)"; then
        log ERROR "K8sSim binary not found. Build it (see modules/k8ssim/README.md) and set K8SSIM_BIN."
        return 1
    fi

    # Fresh cgroup for this run.
    if [[ -d "/sys/fs/cgroup/$CGROUP_NAME" ]]; then
        cgdelete -g memory,cpu:/$CGROUP_NAME 2>/dev/null || true
    fi
    cgcreate -g memory,cpu:/$CGROUP_NAME
    if [[ ! -d "/sys/fs/cgroup/$CGROUP_NAME" ]]; then
        log ERROR "Failed to create cgroup: $CGROUP_NAME"
        return 1
    fi

    # Start the simulator HTTP server inside the cgroup.
    cgexec -g "memory,cpu:/$CGROUP_NAME" "$BIN" > "${LOCAL_PATH}/server.out" 2>&1 &
    K8SSIM_PID=$!

    # Wait for the API to accept requests.
    local up="false"
    for _ in $(seq 1 30); do
        if python3 - "$K8SSIM_SERVER" <<'PY' 2>/dev/null
import sys, json, urllib.request
try:
    req = urllib.request.Request(sys.argv[1] + "/stepResult",
        data=json.dumps({"none": ""}).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=2).read()
    sys.exit(0)
except Exception:
    sys.exit(1)
PY
        then up="true"; break; fi
        kill -0 "$K8SSIM_PID" 2>/dev/null || { log ERROR "K8sSim server exited early"; return 1; }
        sleep 1
    done
    [[ "$up" == "true" ]] || { log ERROR "K8sSim server did not become ready on :$K8SSIM_PORT"; return 1; }
    log INFO "K8sSim server up (pid $K8SSIM_PID, sched $K8SSIM_SCHED)"
}

cluster_setup(){
    [[ -f "$K8SSIM_CONF" ]] || { log ERROR "Scheduler conf not found: $K8SSIM_CONF"; return 1; }
    log INFO "K8sSim setup complete (conf $K8SSIM_CONF)"
}

deploy_objects(){
    local NODE_FILE="$1"
    local WORKLOAD_FILE="$2"
    # Prefer an explicit workload-<N>.yaml next to the node file.
    local NODE_NUM CANDIDATE
    NODE_NUM=$(basename "$NODE_FILE" | grep -o '[0-9]\+' | tail -1)
    CANDIDATE="$(dirname "$NODE_FILE")/workload-${NODE_NUM}.yaml"
    [[ -f "$CANDIDATE" ]] && WORKLOAD_FILE="$CANDIDATE"

    if [[ ! -f "$WORKLOAD_FILE" ]]; then
        log ERROR "Workload file not found: $WORKLOAD_FILE"
        UNSCHEDULED_PODS=0
        return 1
    fi

    log INFO "Driving K8sSim: nodes=$(basename "$NODE_FILE") workload=$(basename "$WORKLOAD_FILE")"
    local OUT
    OUT=$(python3 "${LOCAL_PATH}/k8ssim_driver.py" \
        --server "$K8SSIM_SERVER" \
        --nodes "$NODE_FILE" \
        --workload "$WORKLOAD_FILE" \
        --conf "$K8SSIM_CONF" 2>&1)
    echo "$OUT"
    UNSCHEDULED_PODS=$(awk '/Unscheduled:/ {printf "%d", $2}' <<< "$OUT")
    [[ -z "$UNSCHEDULED_PODS" ]] && UNSCHEDULED_PODS=0
}

watch_pod_scheduling(){
    # The driver runs the simulation to completion synchronously; nothing to poll.
    :;
}

cleanup_cluster(){
    if [[ "$K8SSIM_PID" -gt 0 ]]; then
        kill -TERM "$K8SSIM_PID" 2>/dev/null || true
        sleep 1
        kill -KILL "$K8SSIM_PID" 2>/dev/null || true
        K8SSIM_PID=-1
    fi
    cgdelete -g memory,cpu:/$CGROUP_NAME 2>/dev/null || true
    log INFO "K8sSim cleaned up"
}

log INFO "K8sSim (Volcano) module loaded!"
