#!/usr/bin/env bash
# Every storm: 8 workers, 60 s, one SIGKILL every 500 ms.
set -u
cd "$(dirname "$0")"
export DURATION=60
run() { python3 storm.py "$@" 2>&1 | grep -v NOTICE; echo; }
for seed in 1 2 3; do SEED=$seed TAIL_P=0 run transaction; done > output-storm-transaction.txt
SEED=1 TAIL_P=0 STALE_S=2 run saga lookup > output-storm-lookup-notail.txt
for seed in 1 2 3; do SEED=$seed TAIL_P=0.02 STALE_S=2 run saga lookup; done > output-storm-lookup.txt
SEED=1 TAIL_P=0.02 STALE_S=5 run saga lookup > output-storm-lookup-5s.txt
for seed in 1 2 3; do SEED=$seed TAIL_P=0.02 STALE_S=2 run saga redrive; done > output-storm-redrive.txt
