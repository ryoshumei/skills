#!/bin/sh
# Checks for ../scripts/break-reminder.sh in simulated time. Fake date and sleep
# commands come first on PATH, and sleep moves a clock file forward instead of
# waiting, so an hour passes in a fraction of a second. --dry-run logs the
# sound, dialog and notification instead of showing them.
#
#   sh tests/test-break-reminder.sh

here=$(cd "$(dirname "$0")" && pwd)
script="$here/../scripts/break-reminder.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
failed=0

mkdir "$tmp/bin"
cat > "$tmp/bin/date" <<'EOF'
#!/bin/sh
now=$(cat "$SIM/clock")
case $1 in
  +%s) echo "$now" ;;
  -r) /bin/date -r "$2" "$3" ;;
  *) /bin/date -r "$now" "$1" ;;
esac
EOF
cat > "$tmp/bin/sleep" <<'EOF'
#!/bin/sh
# Move the clock forward by $1 seconds. The Mac sleeps once for SIM_SLEEP_FOR
# seconds after SIM_SLEEP_AT, the user is away from SIM_AWAY_FROM to
# SIM_AWAY_TO, and past SIM_END the loop is stopped (all seconds from 00:00).
now=$(( $(cat "$SIM/clock") + $1 ))
if [ -n "${SIM_SLEEP_AT:-}" ] && [ ! -e "$SIM/slept" ] && [ $((now - T0)) -gt "$SIM_SLEEP_AT" ]; then
  : > "$SIM/slept"
  now=$((now + SIM_SLEEP_FOR))
fi
echo "$now" > "$SIM/clock"
rel=$((now - T0))
idle=0
if [ -n "${SIM_AWAY_FROM:-}" ] && [ $rel -ge "$SIM_AWAY_FROM" ] && [ $rel -lt "$SIM_AWAY_TO" ]; then
  idle=$((rel - SIM_AWAY_FROM))
fi
echo "$idle" > "$SIM/idle"
[ $rel -le "$SIM_END" ] || kill -TERM "$PPID"
EOF
chmod +x "$tmp/bin/date" "$tmp/bin/sleep"

# sim MINUTES [options]: run the loop from 00:00 UTC for MINUTES of simulated
# time, then print its log without the date, and the exit status. Export SIM_*
# first to put the Mac to sleep or send the user away.
sim() {
  SIM=$tmp/sim
  rm -rf "$SIM"; mkdir "$SIM"
  T0=1767225600
  SIM_END=$(($1 * 60)); shift
  echo "$T0" > "$SIM/clock"
  echo 0 > "$SIM/idle"
  export SIM T0 SIM_END
  TZ=UTC PATH="$tmp/bin:$PATH" BREAK_REMINDER_IDLE_FILE="$SIM/idle" \
    sh "$script" --dry-run --log "$SIM/log" "$@" >/dev/null 2>&1
  status=$?
  [ -e "$SIM/log" ] && cut -d' ' -f2- "$SIM/log"
  echo "exit $status"
}

# events: drop the start line and the sound and notification lines.
events() { sed -e 1d -e '/ sound: /d' -e '/ notification: /d'; }

expect() {
  if [ "$2" = "$3" ]; then
    echo "ok   $1"
  else
    printf 'FAIL %s\n--- want\n%s\n--- got\n%s\n' "$1" "$2" "$3"
    failed=1
  fi
}

expect "steady work: a break after 25 minutes, over 5 minutes later" "\
00:00:00 start: a 5-minute break after 25 minutes of activity, away after 15 idle minutes
00:25:00 break
00:25:00 sound: Glass
00:25:00 dialog: Take a 5-minute break
00:30:00 break over
00:30:00 sound: Ping
00:30:00 notification: Break over
00:31:30 stop
exit 0" "$(sim 31)"

export SIM_AWAY_FROM=600 SIM_AWAY_TO=2400
expect "15 minutes without input: away, then 25 minutes from the return" "\
00:25:00 away since 00:10, the clock restarts when you are back
00:40:00 back
01:05:00 break
01:05:00 dialog: Take a 5-minute break
01:10:00 break over
01:10:30 stop
exit 0" "$(sim 70 | events)"
unset SIM_AWAY_FROM SIM_AWAY_TO

export SIM_SLEEP_AT=1200 SIM_SLEEP_FOR=600
expect "a 10-minute sleep counts as a break" "\
00:30:30 asleep 00:20 to 00:30, the clock restarts
00:55:30 break
00:55:30 dialog: Take a 5-minute break
01:00:30 break over
01:02:30 stop
exit 0" "$(sim 62 | events)"

export SIM_SLEEP_AT=600 SIM_SLEEP_FOR=120
expect "a 2-minute sleep counts as work" "\
00:25:00 break
00:25:00 dialog: Take a 5-minute break
00:30:00 break over
00:31:30 stop
exit 0" "$(sim 31 | events)"
unset SIM_SLEEP_AT SIM_SLEEP_FOR

expect "--lang zh, and a stop in the middle of a break" "\
00:25:00 break
00:25:00 dialog: 休息 5 分钟
00:30:00 stop
exit 0" "$(sim 26 --lang zh | events)"

expect "--test shows one dialog, logs the result and exits" "\
00:00:00 sound: Glass
00:00:00 dialog: Test: break reminder
00:00:00 test: seen
exit 0" "$(sim 1 --test)"

for bad in "--work 0" "--work 08" "--rest x" "--bogus" "--work"; do
  # $bad stays unquoted so that "--work 0" becomes two arguments.
  expect "rejects $bad" "exit 2" "$(sim 1 $bad)"
done

exit $failed
