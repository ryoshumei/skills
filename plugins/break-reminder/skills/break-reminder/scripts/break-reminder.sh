#!/bin/sh
# Pomodoro-style break reminder for macOS; how an agent runs it is in ../SKILL.md.
# After --work minutes of keyboard and mouse activity, a sound and a dialog ask
# for a --rest minute break; when it ends, a sound and a notification say so.
# No input for --away minutes restarts the clock, and so does a system sleep of
# at least --rest minutes, which counts as a break taken.
#
#   break-reminder.sh [--work 25] [--rest 5] [--away 15] [--lang en|zh|ja]
#                     [--log FILE] [--test] [--dry-run]
#
# Every start, break, break over, away, back, sleep and stop goes to stdout and
# to --log (~/Library/Logs/break-reminder.log). --test shows one dialog, exits 0
# once its button is clicked and 1 if it isn't within 30 seconds. --dry-run logs
# the sound, dialog and notification instead of showing them and reads the idle
# seconds from the file named in BREAK_REMINDER_IDLE_FILE; the tests also put
# fake date and sleep commands first on PATH.

WORK_MIN=25
REST_MIN=5
AWAY_MIN=15
LANG_CODE=en
LOG="$HOME/Library/Logs/break-reminder.log"
TEST=0
DRY=0
TICK=30

need() { [ "$2" -ge 2 ] || { echo "break-reminder: $1 needs a value" >&2; exit 2; }; }
while [ $# -gt 0 ]; do
  case $1 in
    --work) need "$1" $#; WORK_MIN=$2; shift 2 ;;
    --rest) need "$1" $#; REST_MIN=$2; shift 2 ;;
    --away) need "$1" $#; AWAY_MIN=$2; shift 2 ;;
    --lang) need "$1" $#; LANG_CODE=$2; shift 2 ;;
    --log) need "$1" $#; LOG=$2; shift 2 ;;
    --test) TEST=1; shift ;;
    --dry-run) DRY=1; shift ;;
    *) echo "break-reminder: unknown option $1" >&2; exit 2 ;;
  esac
done
for m in "$WORK_MIN" "$REST_MIN" "$AWAY_MIN"; do
  case $m in
    ''|*[!0-9]*|0*) echo "break-reminder: minutes must be whole numbers above 0, without leading zeros" >&2; exit 2 ;;
  esac
done
if [ $DRY -eq 0 ] && [ "$(uname)" != Darwin ]; then
  echo "break-reminder: needs macOS (ioreg, osascript, afplay)" >&2
  exit 2
fi

case $LANG_CODE in
  zh)
    T_BREAK="休息 $REST_MIN 分钟"; M_BREAK="已专注 $WORK_MIN 分钟：站起来、喝口水、看看远处"
    T_BACK="休息结束"; M_BACK="回来吧，新的 $WORK_MIN 分钟开始"; BUTTON="好"
    T_TEST="测试：休息提醒"; M_TEST="休息提醒会这样弹出来。看到就点「好」" ;;
  ja)
    T_BREAK="${REST_MIN}分休憩"; M_BREAK="${WORK_MIN}分集中しました。立って、水を飲んで、遠くを見ましょう"
    T_BACK="休憩終了"; M_BACK="おかえりなさい。次の${WORK_MIN}分を始めましょう"; BUTTON="OK"
    T_TEST="テスト：休憩リマインダー"; M_TEST="休憩の合図はこう表示されます。見えたら OK を押してください" ;;
  *)
    T_BREAK="Take a $REST_MIN-minute break"; M_BREAK="$WORK_MIN minutes of focus: stand up, drink some water, look into the distance"
    T_BACK="Break over"; M_BACK="Welcome back: the next $WORK_MIN minutes start now"; BUTTON="OK"
    T_TEST="Test: break reminder"; M_TEST="Breaks will show up like this. Click OK if you can see it" ;;
esac

WORK=$((WORK_MIN * 60))
REST=$((REST_MIN * 60))
AWAY=$((AWAY_MIN * 60))

# A background task or login item may lack Homebrew on its PATH.
TN=
for p in "$(command -v terminal-notifier 2>/dev/null)" /opt/homebrew/bin/terminal-notifier /usr/local/bin/terminal-notifier; do
  if [ -n "$p" ] && [ -x "$p" ]; then TN=$p; break; fi
done

# A sandbox can block the log file; stdout still has every line.
log() {
  line="$(date '+%m-%d %H:%M:%S') $*"
  echo "$line"
  { echo "$line" >> "$LOG"; } 2>/dev/null
}
clock() { date -r "$1" '+%H:%M'; }

idle() {
  if [ $DRY -eq 1 ]; then cat "$BREAK_REMINDER_IDLE_FILE" 2>/dev/null || echo 0; return; fi
  /usr/sbin/ioreg -c IOHIDSystem | /usr/bin/awk '/HIDIdleTime/ {print int($NF/1000000000); exit}'
}

# afplay plays even when a Focus mode hides notifications.
sound() {
  if [ $DRY -eq 1 ]; then log "sound: $1"; return; fi
  /usr/bin/afplay "/System/Library/Sounds/$1.aiff" &
}

# The dialog has no default button, so a Return typed mid-sentence leaves it
# open. With "background" it runs beside the loop, which keeps its pid in dpid.
dialog() {
  if [ $DRY -eq 1 ]; then
    log "dialog: $1"
    [ "${4:-}" = background ] || echo "button returned:$BUTTON, gave up:false"
    return
  fi
  script="display dialog \"$2\" with title \"$1\" buttons {\"$BUTTON\"} giving up after $3"
  if [ "${4:-}" = background ]; then
    /usr/bin/osascript -e "$script" >/dev/null 2>&1 &
    dpid=$!
  else
    /usr/bin/osascript -e "$script"
  fi
}

notify() {
  if [ $DRY -eq 1 ]; then log "notification: $1"; return; fi
  if [ -n "$TN" ]; then
    "$TN" -title "$1" -message "$2" -group break-reminder >/dev/null
  else
    /usr/bin/osascript -e "display notification \"$2\" with title \"$1\""
  fi
}

if [ $TEST -eq 1 ]; then
  sound Glass
  result=$(dialog "$T_TEST" "$M_TEST" 30)
  echo "$result"
  case $result in
    *"gave up:false"*) log "test: seen"; exit 0 ;;
    *) log "test: missed"; exit 1 ;;
  esac
fi

# A background sleep with wait, unlike a foreground sleep, lets stop run at once.
nap() { sleep "$1" & spid=$!; wait "$spid"; spid=; }
stop() {
  [ -n "$spid" ] && kill "$spid" 2>/dev/null
  if [ -n "$dpid" ] && ps -p "$dpid" -o comm= 2>/dev/null | grep -q osascript; then
    kill "$dpid"
  fi
  log "stop"
  exit 0
}
spid=
dpid=
trap stop TERM INT HUP

log "start: a $REST_MIN-minute break after $WORK_MIN minutes of activity, away after $AWAY_MIN idle minutes"
start=$(date +%s)
last=$start
away=0
while :; do
  nap "$TICK"
  now=$(date +%s)
  i=$(idle)
  if [ $((now - last)) -ge "$REST" ]; then
    # Checks this far apart mean the Mac slept: a break taken away from the screen.
    log "asleep $(clock "$last") to $(clock "$now"), the clock restarts"
    away=0
    start=$now
  elif [ "${i:-0}" -ge "$AWAY" ]; then
    [ $away -eq 1 ] || log "away since $(clock $((now - i))), the clock restarts when you are back"
    away=1
    start=$now
  elif [ $away -eq 1 ]; then
    away=0
    start=$now
    log "back"
  fi
  last=$now
  if [ $((now - start)) -ge "$WORK" ]; then
    log "break"
    sound Glass
    dialog "$T_BREAK" "$M_BREAK" "$REST" background
    nap "$REST"
    dpid=
    log "break over"
    sound Ping
    notify "$T_BACK" "$M_BACK"
    start=$(date +%s)
    last=$start
  fi
done
