#!/bin/sh
# Restart redroid's lmkd through init when it spins at 100% CPU.
#
# Android 14 lmkd mistakes a pidfd's EPOLLHUP for a dropped data-socket connection, closes
# system_server's socket and decrements maxevents on every loop until epoll_wait returns EINVAL
# forever (AOSP 667fdbfe fixes it; first in android-15.0.0_r20, in no android-14 tag). Linux 6.9+
# raises that EPOLLHUP once the killed process is reaped. A deaf lmkd blocks AMS and the runtime
# restarts every ~90 s. First line of defence is psi_{partial,complete}_stall_ms=0 (no monitors, no
# kills, no pidfd); this is the net under it, and it saves the evidence before repairing.
#
# ponytail: two /proc/stat samples 5 s apart, one restart per 10 min. ctl.restart sets SVC_RESTART,
# which init's critical-crash counter ignores; kill -9 would count (4 in 4 min reboots the container).
set -u
C=${LMKD_WD_CONTAINER:-redroid-poc}
OUT=${LMKD_WD_OUT:-$HOME/redroid-poc/lmkd-watchdog}
THRESH=${LMKD_WD_THRESHOLD:-90}   # percent of one core over the sample
HOLD=${LMKD_WD_HOLD:-600}         # seconds between restarts

pid=$(pgrep -xo lmkd) || exit 0   # container down: nothing to watch
t1=$(awk '{print $14+$15}' "/proc/$pid/stat" 2>/dev/null) || exit 0
sleep 5
t2=$(awk '{print $14+$15}' "/proc/$pid/stat" 2>/dev/null) || exit 0
pct=$(( (t2 - t1) * 100 / (5 * $(getconf CLK_TCK)) ))
[ "$pct" -ge "$THRESH" ] || exit 0

mkdir -p "$OUT"
now=$(date +%s); last=$(cat "$OUT/last-restart" 2>/dev/null || echo 0)
if [ $((now - last)) -lt "$HOLD" ]; then
    echo "lmkd at ${pct}% but restarted $((now - last))s ago; holding"
    exit 0
fi

log=$OUT/$(date +%F-%H%M%S).log
{
    echo "host pid $pid at ${pct}% over 5s"
    # fd 3 is the epoll set on a healthy lmkd; anything else there means fd-number reuse.
    docker exec "$C" sh -c 'p=$(pidof lmkd); echo "container pid $p"; getprop init.svc.lmkd; ls -l /proc/$p/fd; grep -E "^(State|Threads|voluntary|nonvoluntary)" /proc/$p/status'
    # logd is saturated by now: cap the read, then kill the reader it leaves behind.
    timeout 20 docker exec "$C" sh -c 'logcat -d -b main -b system -s lowmemorykiller:* 2>/dev/null | grep -v "epoll_wait failed" | tail -40'
    docker exec "$C" pkill -9 logcat 2>/dev/null
} > "$log" 2>&1
docker exec "$C" setprop ctl.restart lmkd && echo "$now" > "$OUT/last-restart"
echo "lmkd at ${pct}% -> ctl.restart lmkd; forensics in $log"
