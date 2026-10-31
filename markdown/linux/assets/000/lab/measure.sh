#!/usr/bin/env bash
# Timestamped snapshot of system memory and Firefox's share of it.
# Usage: ./measure.sh [PID...] > before.txt   (unload tabs)   ./measure.sh [PID...] > after.txt
# Optional PIDs (from the Processes column of about:unloads) are reported one by one.
set -euo pipefail

echo "=== snapshot $(date --iso-8601=seconds)"
echo

echo "=== machine"
grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '"'
echo "kernel  $(uname -r)"
echo "uptime  $(uptime -p)"
snap list firefox 2>/dev/null | tail -n +2 | awk '{print "firefox " $2 " (snap, rev " $3 ")"}' \
    || dpkg -l firefox 2>/dev/null | awk '/^ii/{print "firefox " $3 " (deb)"}'
echo

echo "=== free -m"
free -m
echo

echo "=== /proc/meminfo (selected)"
grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):' /proc/meminfo
echo

echo "=== /proc/pressure/memory"
cat /proc/pressure/memory
echo

# Every process whose executable lives in a Firefox install: the parent and
# all of its content, extension, GPU and utility children.
firefox_pids=$(pgrep -u "$USER" -f '/(firefox|firefox-bin)( |$)' || true)

rows=$(for pid in $firefox_pids; do
    rollup=/proc/$pid/smaps_rollup
    [[ -r $rollup ]] || continue
    name=$(cat "/proc/$pid/comm")
    awk -v pid="$pid" -v name="$name" '
        /^Rss:/  {rss=$2}
        /^Pss:/  {pss=$2}
        /^Swap:/ {swap=$2}
        END {printf "%-8s %10d %10d %10d  %s\n", pid, pss, rss, swap, name}
    ' "$rollup"
done | sort -k2,2nr)

echo "=== firefox processes (kB; PSS splits shared pages, RSS counts them in every process)"
printf '%-8s %10s %10s %10s  %s\n' PID PSS RSS SWAP NAME
head -15 <<<"$rows"
echo "..."
echo

if (( $# > 0 )); then
    echo "=== watched processes (kB)"
    printf '%-8s %10s %10s\n' PID PSS SWAP
    for pid in "$@"; do
        if [[ -r /proc/$pid/smaps_rollup ]]; then
            awk -v pid="$pid" '/^Pss:/{pss=$2} /^Swap:/{swap=$2}
                END {printf "%-8s %10d %10d\n", pid, pss, swap}' "/proc/$pid/smaps_rollup"
        else
            printf '%-8s %10s %10s\n' "$pid" exited -
        fi
    done
    echo
fi

echo "=== firefox totals"
awk '{n++; pss+=$2; rss+=$3; swap+=$4}
     END {printf "processes  %d\nPSS        %.0f MiB\nRSS (sum)  %.0f MiB\nswap       %.0f MiB\n",
          n, pss/1024, rss/1024, swap/1024}' <<<"$rows"
