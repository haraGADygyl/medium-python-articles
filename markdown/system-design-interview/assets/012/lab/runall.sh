#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
P=.venv/bin/python
for i in 1 2 3; do $P race.py plain > out/plain-$i.txt; done
$P race.py plain --stall-p 0 > out/plain-nostall.txt
$P race.py delete-first > out/delete-first.txt
for d in 0.1 0.5 1 2; do $P race.py double --delay $d > out/double-$d.txt; done
for i in 1 2 3; do $P race.py versioned > out/versioned-$i.txt; done
for i in 1 2 3; do $P race.py tombstone > out/tombstone-$i.txt; done
echo done
