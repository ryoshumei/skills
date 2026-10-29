---
name: break-reminder
description: "Pomodoro-style break reminders on macOS: a sound and a dialog after 25 minutes of keyboard and mouse activity, a notification when the 5-minute break ends, and time away from the desk restarts the clock. Use when the user asks to be reminded to rest or take breaks (每25分钟提醒我休息, 番茄钟, 休憩リマインダー, ポモドーロ), asks whether the reminder is running or why it stayed quiet, or wants to change or stop it."
---

# Break reminder

`<skill-dir>/scripts/break-reminder.sh` is a POSIX shell loop that you run as a background task. `<skill-dir>` is this skill's base directory, which Claude Code shows when the skill loads. It needs macOS: `ioreg`, `osascript` and `afplay` ship with it, and `terminal-notifier`, when installed, shows the end-of-break banner.

The loop's process matches the pattern `'^(/bin/)?sh .*break-reminder\.sh'`. Use it with `pgrep -fl` to find the loop and with `pkill -f` to stop it; it matches the shell running the script and nothing that merely names the file.

## Start

1. Read the settings from the request: `--work` minutes of activity before a break (25), `--rest` minutes of break (5), `--away` minutes without input that count as being away (15), and `--lang en|zh|ja` for the user's language.
2. If `~/Library/Logs/break-reminder.log` doesn't exist yet, this is the first run on this Mac. Show a test dialog in the foreground: `sh <skill-dir>/scripts/break-reminder.sh --test --lang zh`. It exits 0 once the user clicks the button. Exit 1 (30 seconds without a click) or an error means the dialog didn't reach them: tell the user and stop here.
3. Run one loop at a time: `pkill -f` with the pattern stops an earlier one, and its exit status 1 only means none was running.
4. Start it with the Bash tool's `run_in_background`: `exec sh <skill-dir>/scripts/break-reminder.sh --work 25 --rest 5 --lang zh`.
5. Tell the user when the first break comes (now plus `--work` minutes, if they stay at the desk) and how to stop it.

Done when `pgrep -fl` with the pattern shows exactly one loop and the user knows when the first break comes.

## Check, change, stop

- **Is it running, and why was it quiet?** `pgrep -fl` with the pattern shows the loop and its flags. The log (`~/Library/Logs/break-reminder.log`, or the `--log` file) has a timestamped line for every start, break, break over, away, back, sleep and stop, so a quiet stretch shows up as an `away since` or `asleep` line. Answer with those times. If the log is missing (a sandbox can block writes outside the project), read the background task's output, which has the same lines.
- **Change:** read the current flags from `pgrep -fl`, stop the loop, and start it again with the new values and the other flags kept. The clock restarts.
- **Stop:** `pkill -f` with the pattern. The loop closes an open break dialog, logs `stop` and exits.

## How it behaves, and why

- It counts activity, not wall time. No keyboard or mouse input for `--away` minutes means the user is away, and the clock restarts when they are back, so nights and lunch stay quiet. With `--away 5`, watching a video or waiting on an agent kept restarting it and no break came for hours; 15 keeps short pauses inside the work stretch.
- A system sleep of at least `--rest` minutes counts as a break taken, since the screen was off, and restarts the clock; a shorter one counts as work.
- The break prompt is a dialog plus a sound, because a banner fired on time and went unseen, and Focus modes hide banners. The dialog stays until its button is clicked or the break ends, and `afplay` plays even under Focus. The dialog has no default button, so a Return typed mid-sentence leaves it open.
- The end of the break is a sound plus a notification, since the user is usually away from the screen by then.
- The loop runs as a background task of the session that started it. Whether it outlives that session depends on how Claude Code runs, so after a restart check with `pgrep` before starting another. A login item (a LaunchAgent) would start it at every login; create one only when the user explicitly asks, and stop that one with `launchctl bootout`, since launchd restarts a killed job.
