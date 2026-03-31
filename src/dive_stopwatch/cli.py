"""Command-line interface for the stopwatch prototype."""

from __future__ import annotations

from dive_stopwatch.dive_mode import DiveController, DivePhase
from dive_stopwatch.stopwatch import DeviceMode, StopwatchManager, format_hhmmss


HELP_TEXT = """
Commands:
  mode                         Toggle mode (STOPWATCH <-> DIVE)
  use <name>                   Select active stopwatch (creates if missing)
  list                         List stopwatches
  startstop                    Toggle start/pause on active stopwatch
  start                        Start active stopwatch
  stop                         Stop/pause active stopwatch
  reset                        Reset active stopwatch (only when stopped)
  lap                          LAP on active stopwatch
  split                        SPLIT toggle (freeze/unfreeze) on active stopwatch
  time                         Show display time + live total for active stopwatch
  marks                        Show marks for active stopwatch
  status                       Show current dive-mode status
  help                         Show commands
  quit
"""


def main() -> None:
    mode = DeviceMode.STOPWATCH
    manager = StopwatchManager()
    active_name = "main"
    stopwatch = manager.get(active_name)
    dive = DiveController()

    print("Seiko-like Stopwatch Prototype")
    print(HELP_TEXT.strip())

    while True:
        try:
            raw = input(f"[mode={mode.name} timer={active_name}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        parts = raw.split()
        command = parts[0].lower()

        if command in {"quit", "exit", "q"}:
            break

        if command == "help":
            print(HELP_TEXT.strip())
            continue

        if command == "mode":
            mode = DeviceMode.DIVE if mode is DeviceMode.STOPWATCH else DeviceMode.STOPWATCH
            print(f"Mode set to {mode.name}.")
            continue

        if command == "use":
            if len(parts) != 2:
                print("Usage: use <name>")
                continue
            active_name = parts[1]
            stopwatch = manager.get(active_name)
            continue

        if command == "list":
            names = manager.names()
            print("Timers:", ", ".join(names) if names else "(none)")
            continue

        try:
            if command == "startstop":
                if mode is DeviceMode.DIVE:
                    if dive.phase is DivePhase.READY:
                        result = dive.start()
                        print(f"{result['event']} {result['clock']}")
                    elif dive.phase is DivePhase.ASCENT:
                        result = dive.stop()
                        print(
                            f"{result['event']} {result['clock']}  "
                            f"AT={result['AT']} TDT={result['TDT']} TTD={result['TTD']}  "
                            f"CT={result['CT']}"
                        )
                    else:
                        raise RuntimeError(
                            "In dive mode, start/stop is only used at LS and RS."
                        )
                    continue
                stopwatch.start_stop()
                print("Running." if stopwatch.running else "Paused.")
            elif command == "start":
                if mode is DeviceMode.DIVE:
                    result = dive.start()
                    print(f"{result['event']} {result['clock']}")
                    continue
                stopwatch.start()
                print("Running.")
            elif command == "stop":
                if mode is DeviceMode.DIVE:
                    result = dive.stop()
                    print(
                        f"{result['event']} {result['clock']}  "
                        f"AT={result['AT']} TDT={result['TDT']} TTD={result['TTD']}  "
                        f"CT={result['CT']}"
                    )
                    continue
                stopwatch.stop()
                print("Paused.")
            elif command == "reset":
                if mode is DeviceMode.DIVE:
                    dive.reset()
                    print("Dive session cleared.")
                    continue
                stopwatch.reset()
                print("Reset to 00:00:00.000")
            elif command == "lap":
                if mode is DeviceMode.DIVE:
                    result = dive.lap()
                    if result["event"] == "RB":
                        print(f"RB {result['clock']}  DT={result['DT']}")
                    elif result["event"] == "LB":
                        print(f"LB {result['clock']}  BT={result['BT']}")
                    else:
                        print(f"{result['event']}{result['stop_number']} {result['clock']}")
                    continue
                mark = stopwatch.lap()
                print(
                    f"{mark.kind} #{mark.index}: "
                    f"lap={format_hhmmss(mark.lap_seconds)} "
                    f"total={format_hhmmss(mark.total_seconds)}"
                )
            elif command == "split":
                if mode is DeviceMode.DIVE:
                    raise RuntimeError("Use lap in dive mode; split is interpreted automatically.")
                mark = stopwatch.split()
                if mark.kind == "SPLIT":
                    print(
                        f"SPLIT(FREEZE) #{mark.index}: "
                        f"lap={format_hhmmss(mark.lap_seconds)} "
                        f"total={format_hhmmss(mark.total_seconds)}"
                    )
                else:
                    print("SPLIT released (display live).")
            elif command == "time":
                if mode is DeviceMode.DIVE:
                    if dive.phase is DivePhase.CLEAN_TIME:
                        status = dive.clean_time_status()
                        print(
                            f"phase={dive.phase.name} CT={status['CT']} complete={status['complete']}"
                        )
                    else:
                        print(f"phase={dive.phase.name} events={dive.session.summary()}")
                    continue
                display = stopwatch.display_time()
                live = stopwatch.total_elapsed()
                frozen = stopwatch._frozen_display_total is not None
                print(
                    f"display={format_hhmmss(display)}  "
                    f"live={format_hhmmss(live)}  "
                    f"running={stopwatch.running} frozen={frozen}"
                )
            elif command == "marks":
                if mode is DeviceMode.DIVE:
                    if dive.stop_events:
                        print(
                            {
                                "events": dive.session.summary(),
                                "stop_events": [
                                    f"{event.code}{event.stop_number} {event.timestamp.strftime('%H:%M:%S')}"
                                    for event in dive.stop_events
                                ],
                            }
                        )
                    else:
                        print(dive.session.summary() or "(no dive events)")
                    continue
                if not stopwatch.marks:
                    print("(no marks)")
                else:
                    for mark in stopwatch.marks:
                        print(
                            f"{mark.index:>3} {mark.kind:<13} "
                            f"lap={format_hhmmss(mark.lap_seconds)} "
                            f"total={format_hhmmss(mark.total_seconds)}"
                        )
            elif command == "status":
                if mode is DeviceMode.DIVE:
                    if dive.phase is DivePhase.CLEAN_TIME:
                        status = dive.clean_time_status()
                        print(
                            f"phase={dive.phase.name} events={dive.session.summary()} "
                            f"last_stop={_format_stop_event(dive.latest_stop_event())} CT={status['CT']}"
                        )
                    else:
                        print(
                            f"phase={dive.phase.name} events={dive.session.summary()} "
                            f"last_stop={_format_stop_event(dive.latest_stop_event())}"
                        )
                else:
                    print("Status is only used in dive mode.")
            else:
                print("Unknown command. Type 'help'.")
        except RuntimeError as exc:
            print(f"Error: {exc}")


def _format_stop_event(event: object) -> str:
    if event is None:
        return "None"
    return f"{event.code}{event.stop_number} {event.timestamp.strftime('%H:%M:%S')}"
