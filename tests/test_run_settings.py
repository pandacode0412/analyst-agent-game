"""Run block resolution: start/stop instants in Asia/Ho_Chi_Minh and CLI precedence."""
import unittest
from datetime import datetime, timezone

from agent.run_settings import RunConfig, load_run_config, plan_run


def utc(local_clock: str, day: int = 8) -> datetime:
    """Local 'HH:MM' on 2026-11-<day> (UTC+7) expressed in UTC."""
    hours, minutes = map(int, local_clock.split(":"))
    return datetime(2026, 11, day, hours, minutes, tzinfo=timezone.utc).replace(
        hour=(hours - 7) % 24, day=day if hours >= 7 else day - 1)


def local(moment: datetime) -> str:
    from agent.analytics import TZ
    return moment.astimezone(TZ).strftime("%d %H:%M")


class RunSettingsTests(unittest.TestCase):
    def test_waits_for_start_and_stops_same_day(self):
        plan = plan_run(load_run_config({"start_at": "07:00", "stop_at": "21:00"}), utc("05:30"))
        self.assertEqual((local(plan.start_utc), local(plan.stop_utc)), ("08 07:00", "08 21:00"))
        self.assertEqual(plan.iterations, 0)  # run until stop_at
        self.assertEqual(str(plan.report_day), "2026-11-08")

    def test_inside_window_starts_now(self):
        plan = plan_run(load_run_config({"start_at": "07:00", "stop_at": "21:00"}), utc("10:15"))
        self.assertEqual((local(plan.start_utc), local(plan.stop_utc)), ("08 10:15", "08 21:00"))

    def test_after_stop_waits_for_tomorrow(self):
        plan = plan_run(load_run_config({"start_at": "07:00", "stop_at": "21:00"}), utc("22:30"))
        self.assertEqual((local(plan.start_utc), local(plan.stop_utc)), ("09 07:00", "09 21:00"))
        self.assertEqual(str(plan.report_day), "2026-11-09")

    def test_overnight_and_duration(self):
        plan = plan_run(load_run_config({"start_at": "21:00", "stop_at": "07:00"}), utc("20:00"))
        self.assertEqual((local(plan.start_utc), local(plan.stop_utc)), ("08 21:00", "09 07:00"))
        plan = plan_run(load_run_config({"duration_minutes": 15, "stop_at": "23:00"}), utc("22:50"))
        self.assertEqual(local(plan.stop_utc), "08 23:00")  # the earlier stop wins
        plan = plan_run(load_run_config({"duration_minutes": 15}), utc("10:00"))
        self.assertEqual(local(plan.stop_utc), "08 10:15")

    def test_cli_overrides_and_defaults(self):
        config = load_run_config({"interval_seconds": 1, "report_on_exit": True,
                                  "report_window": {"start": "08:00", "end": "20:00"}})
        plan = plan_run(config, utc("10:00"), iterations=20, interval=2.5, report_start="00:00")
        self.assertEqual((plan.iterations, plan.interval_seconds), (20, 2.5))
        self.assertEqual((plan.report_start, plan.report_end, plan.report_on_exit), ("00:00", "20:00", True))
        legacy = plan_run(RunConfig(), utc("10:00"))
        self.assertEqual((legacy.iterations, legacy.interval_seconds, legacy.stop_utc), (3, 5.0, None))
        self.assertFalse(legacy.trusted_round_ids)
        self.assertTrue(plan_run(RunConfig(), utc("10:00"), trusted=True).trusted_round_ids)

    def test_start_now_and_duration_override(self):
        config = load_run_config({"start_at": "07:00", "stop_at": "21:00", "duration_minutes": 600})
        plan = plan_run(config, utc("22:40"), start_now=True, duration_minutes=15)
        self.assertEqual((local(plan.start_utc), local(plan.stop_utc)), ("08 22:40", "08 22:55"))
        self.assertEqual(plan.iterations, 0)
        with self.assertRaises(ValueError):
            plan_run(config, utc("22:40"), duration_minutes=0)

    def test_validation(self):
        for bad in ({"start_at": "25:00"}, {"stop_at": "24:00"}, {"unknown": 1}, {"interval_seconds": 0},
                    {"duration_minutes": -5}, {"report_on_exit": "yes"}, {"login_reminder_seconds": 5},
                    {"report_window": {"from": "07:00"}}, "x"):
            with self.assertRaises(ValueError, msg=bad):
                load_run_config(bad)
        with self.assertRaises(ValueError):
            plan_run(RunConfig(), datetime(2026, 11, 8, 10, 0))


if __name__ == "__main__":
    unittest.main()
