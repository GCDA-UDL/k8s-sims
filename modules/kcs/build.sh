#!/bin/bash
# Build the kcs-yamlsim binary from the pinned pfn k8s-cluster-simulator commit.
#
# The upstream repo is GOPATH-era (no go.mod; dep + vendored). We build in legacy
# GOPATH mode (GO111MODULE=off) so the vendored deps resolve. Our custom entry
# point (modules/kcs/sim/{main,submitter}.go) is dropped into cmd/yamlsim/ of the
# checked-out tree and built. Verified with Go 1.24.4 (~13 s, 37 MB binary).
#
# Usage: bash modules/kcs/build.sh [output-path]   (default: modules/kcs/kcs-yamlsim)
set -euo pipefail

PIN="55e4108275b4704bc35dfc4eb4774f6d1be597c3"   # 2019-04-15
REPO="https://github.com/pfnet-research/k8s-cluster-simulator.git"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$HERE/kcs-yamlsim}"

GP="$(go env GOPATH)"
DST="$GP/src/github.com/pfnet-research/k8s-cluster-simulator"

if [[ ! -d "$DST/.git" ]]; then
    mkdir -p "$(dirname "$DST")"
    git clone "$REPO" "$DST"
fi
git -C "$DST" checkout -q "$PIN"

mkdir -p "$DST/cmd/yamlsim"
cp "$HERE/sim/main.go" "$HERE/sim/submitter.go" "$DST/cmd/yamlsim/"

( cd "$DST" && GO111MODULE=off go build -o "$OUT" ./cmd/yamlsim )
echo "built: $OUT"
