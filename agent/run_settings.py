"""Resolve a source config's optional `run:` block plus CLI overrides into concrete settings.

Pure functions so start/stop rules can be tested without a browser or database
(docs/17-source-integration.md, "Run settings").
"""
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone

from .analytics import TZ
from .streak_window import parse_clock

RUN_FIELDS = {"start_at", "stop_at", "duration_minutes", "interval_seconds", "trusted_round_ids",
              "report_on_exit", "report_window", "report_dir", "login_reminder_seconds"}


@dataclass(frozen=True)
class RunConfig:
    start_at: str | None = None
    stop_at: str | None = None
    duration_minutes: float | None = None
    interval_seconds: float = 5.0
    trusted_round_ids: bool = False
    report_on_exit: bool = False
    report_start: str = "07:00"
    report_end: str = "21:00"
    report_dir: str = "output/reports"
    login_reminder_seconds: float = 300


def _clock(value) -> str:
    text = str(value).strip()
    hours, minutes = parse_clock(text)
    if hours == 24:
        raise ValueError("run times must be between 00:00 and 23:59")
    return f"{hours:02d}:{minutes:02d}"


def load_run_config(block) -> RunConfig:
    if block is None:
        return RunConfig()
    if not isinstance(block, dict):
        raise ValueError("run must be an object")
    unknown = set(block) - RUN_FIELDS
    if unknown:
        raise ValueError(f"unknown run fields: {', '.join(sorted(unknown))}")
    window = block.get("report_window") or {}
    if not isinstance(window, dict) or set(window) - {"start", "end"}:
        raise ValueError("run.report_window must be {start, end}")
    config = RunConfig(
        start_at=_clock(block["start_at"]) if block.get("start_at") else None,
        stop_at=_clock(block["stop_at"]) if block.get("stop_at") else None,
        duration_minutes=float(block["duration_minutes"]) if block.get("duration_minutes") else None,
        interval_seconds=float(block.get("interval_seconds", 5.0)),
        trusted_round_ids=_flag(block.get("trusted_round_ids", False), "trusted_round_ids"),
        report_on_exit=_flag(block.get("report_on_exit", False), "report_on_exit"),
        report_start=str(window.get("start", "07:00")),
        report_end=str(window.get("end", "21:00")),
        report_dir=str(block.get("report_dir", "output/reports")),
        login_reminder_seconds=float(block.get("login_reminder_seconds", 300)),
    )
    if config.interval_seconds <= 0 or config.login_reminder_seconds < 30:
        raise ValueError("interval_seconds must be positive and login_reminder_seconds at least 30")
    if config.duration_minutes is not None and config.duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")
    parse_clock(config.report_start), parse_clock(config.report_end)
    return config


def _flag(value, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"run.{name} must be true or false")
    return value


@dataclass(frozen=True)
class RunPlan:
    start_utc: datetime
    stop_utc: datetime | None
    iterations: int
    interval_seconds: float
    trusted_round_ids: bool
    report_on_exit: bool
    report_start: str
    report_end: str
    report_dir: str
    report_day: date
    login_reminder_seconds: float


def _local(day: date, clock: str) -> datetime:
    hours, minutes = parse_clock(clock)
    return datetime.combine(day, time(hours, minutes), tzinfo=TZ)


def plan_run(config: RunConfig, now_utc: datetime, *, iterations: int | None = None,
             interval: float | None = None, trusted: bool | None = None,
             report_on_exit: bool | None = None, report_start: str | None = None,
             report_end: str | None = None, report_dir: str | None = None,
             start_now: bool = False, duration_minutes: float | None = None) -> RunPlan:
    """Apply CLI overrides (non-None) to the run block and compute start/stop instants.

    start_now ignores start_at; duration_minutes replaces run.duration_minutes (a quick test).
    """
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    if duration_minutes is not None:
        if duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")
        config = replace(config, duration_minutes=duration_minutes)
    now = now_utc.astimezone(TZ)
    start = now
    if config.start_at and not start_now:
        start = _local(now.date(), config.start_at)
        if start <= now:
            start = now
            if config.stop_at and _local(now.date(), config.stop_at) <= now \
                    and _local(now.date(), config.stop_at) > _local(now.date(), config.start_at):
                start = _local(now.date() + timedelta(days=1), config.start_at)
    stops = []
    if config.stop_at:
        stop = _local(start.date(), config.stop_at)
        if stop <= start:
            stop += timedelta(days=1)
        stops.append(stop)
    if config.duration_minutes:
        stops.append(start + timedelta(minutes=config.duration_minutes))
    stop = min(stops) if stops else None
    if iterations is None:
        iterations = 0 if stop else 3
    if iterations < 0:
        raise ValueError("iterations must be nonnegative")
    return RunPlan(
        start_utc=start.astimezone(timezone.utc),
        stop_utc=stop.astimezone(timezone.utc) if stop else None,
        iterations=iterations,
        interval_seconds=interval if interval is not None else config.interval_seconds,
        trusted_round_ids=bool(trusted) if trusted else config.trusted_round_ids,
        report_on_exit=bool(report_on_exit) if report_on_exit else config.report_on_exit,
        report_start=report_start or config.report_start,
        report_end=report_end or config.report_end,
        report_dir=report_dir or config.report_dir,
        report_day=start.date(),
        login_reminder_seconds=config.login_reminder_seconds,
    )
