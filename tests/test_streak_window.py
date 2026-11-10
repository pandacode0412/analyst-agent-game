"""Acceptance cases A17–A20 for the Banker/Player reached-13 window metric (docs/07)."""
import unittest
from datetime import date, datetime

from agent.streak_window import (STRICT, TIE_TRANSPARENT, count_run_events,
                                 lookback_complete, window_bounds)

DAY = date(2026, 10, 19)


def rnd(table: str, number: int, utc: str, result: str = "BANKER", source: str = "TEST") -> dict:
    """utc is 'YYYY-MM-DDTHH:MM' or 'HH:MM' on 2026-10-19 (UTC; local = UTC+7)."""
    stamp = utc if "T" in utc else "2026-10-19T" + utc
    return {"event_id": number, "table_id": table,
            "at_utc": datetime.fromisoformat(stamp + ":00+00:00"),
            "kind": "ROUND", "result": result, "round_id": f"R{number}", "source": source}


def gap(table: str, number: int, utc: str) -> dict:
    return {"event_id": number, "table_id": table,
            "at_utc": datetime.fromisoformat("2026-10-19T" + utc + ":00+00:00"),
            "kind": "GAP", "result": None, "round_id": None, "source": None}


def run(table: str, first: int, count: int, hour: int, result: str = "BANKER") -> list[dict]:
    return [rnd(table, first + i, f"{hour:02d}:{i:02d}", result) for i in range(count)]


class StreakWindowTests(unittest.TestCase):
    def setUp(self):
        self.start, self.end = window_bounds(DAY)  # local 07:00–21:00 = 00:00–14:00 UTC

    def count(self, rows, policy):
        return count_run_events(rows, self.start, self.end, policy)

    def test_a17_tie_policies_differ(self):
        rows = run("B51", 0, 6, 1) + [rnd("B51", 6, "01:06", "TIE")]
        rows += [rnd("B51", 7 + i, f"01:{7 + i:02d}") for i in range(7)]
        self.assertEqual(self.count(rows, STRICT), [])
        found = self.count(rows, TIE_TRANSPARENT)
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["side"], found[0]["first_round_id"], found[0]["thirteenth_round_id"]),
                         ("BANKER", "R0", "R13"))

    def test_a18_both_sides_counted_separately(self):
        rows = run("B51", 0, 13, 1, "BANKER") + run("B51", 20, 13, 2, "PLAYER")
        for policy in (STRICT, TIE_TRANSPARENT):
            sides = [item["side"] for item in self.count(rows, policy)]
            self.assertEqual(sides, ["BANKER", "PLAYER"])

    def test_a18_long_run_counts_once_and_tables_independent(self):
        rows = run("B51", 0, 20, 1) + run("B20", 100, 13, 3, "PLAYER")
        found = self.count(rows, STRICT)
        self.assertEqual([(item["table_id"], item["side"]) for item in found],
                         [("B20", "PLAYER"), ("B51", "BANKER")])

    def test_a19_window_assignment(self):
        # 13th Banker at 01:12 UTC = 08:12 local.
        rows = run("B51", 0, 13, 1)
        for start, end, expected in (("07:00", "21:00", 1), ("00:00", "24:00", 1), ("09:00", "21:00", 0)):
            low, high = window_bounds(DAY, start, end)
            self.assertEqual(len(count_run_events(rows, low, high, STRICT)), expected, (start, end))
        # 13th result exactly at 21:00 local (14:00 UTC) is outside; run begun before 07:00 counts once.
        late = run("B20", 0, 12, 13) + [rnd("B20", 12, "14:00")]
        early = [rnd("B30", i, f"2026-10-18T23:{i:02d}") for i in range(12)] + [rnd("B30", 12, "00:00")]
        early += [rnd("B30", 13, "00:01")]
        found = self.count(late + early, STRICT)
        self.assertEqual([(item["table_id"], item["thirteenth_round_id"]) for item in found], [("B30", "R12")])

    def test_gap_and_source_change_break_both_policies(self):
        rows = run("B51", 0, 6, 1) + [gap("B51", 50, "01:06")]
        rows += [rnd("B51", 7 + i, f"01:{7 + i:02d}") for i in range(7)]
        changed = run("B20", 0, 6, 2) + [rnd("B20", 6 + i, f"02:{6 + i:02d}", source="OTHER") for i in range(7)]
        for policy in (STRICT, TIE_TRANSPARENT):
            self.assertEqual(self.count(rows + changed, policy), [])

    def test_a20_invalid_windows_rejected(self):
        for start, end in (("21:00", "07:00"), ("07:00", "07:00"), ("22:00", "02:00"),
                           ("7", "21:00"), ("07:00", "24:01"), ("25:00", "26:00")):
            with self.assertRaises(ValueError, msg=(start, end)):
                window_bounds(DAY, start, end)
        with self.assertRaises(ValueError):
            count_run_events([], self.start, self.end, "unknown_policy")

    def test_a20_long_tie_transparent_lookback(self):
        # Newest first: 30 Ties then 12 Bankers. A fixed 13-row lookback would miss the run.
        prior_desc = [rnd("B51", 100 + i, f"2026-10-18T22:{59 - i:02d}", "TIE") for i in range(30)]
        self.assertFalse(lookback_complete(prior_desc))
        prior_desc += [rnd("B51", i, f"2026-10-18T21:{59 - i:02d}") for i in range(12)]
        self.assertFalse(lookback_complete(prior_desc))
        prior_desc.append(rnd("B51", 99, "2026-10-18T20:00", "PLAYER"))
        self.assertTrue(lookback_complete(prior_desc))
        rows = list(reversed(prior_desc)) + [rnd("B51", 200, "00:30")]
        self.assertEqual(len(self.count(rows, TIE_TRANSPARENT)), 1)
        self.assertEqual(self.count(rows, STRICT), [])
        self.assertTrue(lookback_complete([gap("B51", 1, "00:00")]))


if __name__ == "__main__":
    unittest.main()
