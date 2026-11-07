"""Boundary and continuity checks for the requested 13-red window metric."""
import unittest
from datetime import date, datetime

from agent.red_window import count_red_events, window_bounds


def event(table: str, number: int, clock: str, result: str = "BANKER") -> dict:
    return {"event_id": number, "table_id": table,
            "at_utc": datetime.fromisoformat("2026-10-19T" + clock + "+00:00"),
            "kind": "ROUND", "result": result, "round_id": f"R{number}", "source": "TEST"}


class RedWindowTests(unittest.TestCase):
    def test_crosses_start_and_long_run_counts_once(self):
        start, end = window_bounds(date(2026, 10, 19))
        rows = [event("B51", i, f"{23 if i < 12 else 0:02d}:{i if i < 12 else i - 12:02d}:00")
                for i in range(15)]
        # Put the twelve prior rounds on the preceding UTC date.
        for row in rows[:12]:
            row["at_utc"] = row["at_utc"].replace(day=18)
        found = count_red_events(rows, "BANKER", start, end)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["thirteenth_round_id"], "R12")

    def test_prior_threshold_does_not_repeat_and_end_is_exclusive(self):
        start, end = window_bounds(date(2026, 10, 19))
        rows = [event("B51", i, f"{23 if i < 13 else 0:02d}:{i if i < 13 else i - 13:02d}:00")
                for i in range(15)]
        for row in rows[:13]:
            row["at_utc"] = row["at_utc"].replace(day=18)
        self.assertEqual(count_red_events(rows, "BANKER", start, end), [])
        rows = [event("B20", i, f"13:{i:02d}:00") for i in range(12)]
        rows.append(event("B20", 12, "14:00:00"))  # 21:00 local
        self.assertEqual(count_red_events(rows, "BANKER", start, end), [])

    def test_gap_tie_and_table_identity(self):
        start, end = window_bounds(date(2026, 10, 19))
        rows = [event("B51", i, f"00:{i:02d}:00") for i in range(12)]
        rows.append({"event_id": 20, "table_id": "B51",
                     "at_utc": datetime.fromisoformat("2026-10-19T00:30:00+00:00"),
                     "kind": "GAP", "result": None, "round_id": None, "source": None})
        rows.extend(event("B51", i + 21, f"01:{i:02d}:00") for i in range(13))
        rows.extend(event("B20", i + 50, f"02:{i:02d}:00") for i in range(13))
        rows.append(event("B20", 90, "03:00:00", "TIE"))
        rows.append(event("B20", 91, "03:01:00"))
        found = count_red_events(rows, "BANKER", start, end)
        self.assertEqual([item["table_id"] for item in found], ["B20", "B51"])
        self.assertEqual(found[1]["first_round_id"], "R21")

    def test_requires_explicit_color_mapping(self):
        start, end = window_bounds(date(2026, 10, 19))
        with self.assertRaises(ValueError):
            count_red_events([], "RED", start, end)

    def test_source_change_breaks_table_run(self):
        start, end = window_bounds(date(2026, 10, 19))
        rows = [event("B51", i, f"00:{i:02d}:00") for i in range(13)]
        rows[12]["source"] = "OTHER_SOURCE"
        self.assertEqual(count_red_events(rows, "BANKER", start, end), [])


if __name__ == "__main__":
    unittest.main()
