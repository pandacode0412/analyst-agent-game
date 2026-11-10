"""Counter tracker (evidence level B2): rounds only from consistent +1 counter steps."""
import unittest

from agent.adapters.lobby_counters import CounterTracker, load_lobby_config, parse_counters
from agent.round_validator import ConservativeRoundValidator, TableEvidence


def card(counts, countdown="", card_id="2636"):
    return {"card_id": card_id, "name": "极速百家乐B06", "countdown": countdown,
            "counts": [str(c) for c in counts] + ["1", "0"]}


def run(tracker, cards):
    return [tracker.observe(c, f"2026-11-07T14:00:{i:02d}+00:00") for i, c in enumerate(cards)]


def confirm(states):
    """Feed tracker output through the real validator, as the coordinator does."""
    validator, done = ConservativeRoundValidator("B06"), []
    for index, state in enumerate(states):
        round_id = f"{state['shoe_id']}:{state['round_id']}" if state.get("round_id") else None
        verified = validator.accept(TableEvidence("B06", f"f{index}", state["phase"], round_id,
                                                  state["final_result"], state["roadmap_revision"], True))
        if verified:
            done.append((verified.source_round_id.rsplit(":", 1)[-1], verified.result))
    return done


class CounterTrackerTests(unittest.TestCase):
    def test_parse_requires_consistent_counts(self):
        self.assertEqual(parse_counters(["21", "6", "14", "1", "1", "1"]), (21, 6, 14, 1))
        for bad in (["21", "6", "14", "2"], ["x", "1", "1", "0"], ["3", "1"], ["-1", "0", "0", "-1"]):
            self.assertIsNone(parse_counters(bad), bad)

    def test_one_round_with_repeated_frames(self):
        tracker = CounterTracker("B06")
        states = run(tracker, [card([20, 6, 13, 1], "9"), card([20, 6, 13, 1], "8"),
                               card([20, 6, 13, 1]), card([20, 6, 13, 1]),
                               card([21, 6, 14, 1]), card([21, 6, 14, 1]), card([21, 6, 14, 1]),
                               card([21, 6, 14, 1], "15")])
        self.assertEqual([s["phase"] for s in states],
                         ["BETTING", "BETTING", "DEALING", "DEALING", "RESULT", "RESULT", "RESULT", "BETTING"])
        self.assertEqual(states[4]["final_result"], "PLAYER")
        self.assertEqual(states[7]["round_id"], "22")
        self.assertEqual(confirm(states), [("21", "PLAYER")])

    def test_tie_and_banker_sequence(self):
        tracker = CounterTracker("B06")
        cards = []
        for before, after in (([5, 2, 2, 1], [6, 2, 2, 2]), ([6, 2, 2, 2], [7, 3, 2, 2])):
            cards += [card(before, "10"), card(before), card(after), card(after)]
        self.assertEqual(confirm(run(tracker, cards)), [("6", "TIE"), ("7", "BANKER")])

    def test_skipped_rounds_and_inconsistent_delta_fail_closed(self):
        tracker = CounterTracker("B06")
        states = run(tracker, [card([5, 2, 2, 1], "10"), card([5, 2, 2, 1]),
                               card([7, 3, 3, 1]), card([7, 3, 3, 1])])
        self.assertEqual(states[2]["phase"], "UNKNOWN")
        self.assertEqual(states[2]["reason"], "ROUNDS_SKIPPED")
        self.assertEqual(confirm(states), [])
        tracker = CounterTracker("B06")
        states = run(tracker, [card([5, 2, 2, 1], "10"), card([5, 3, 1, 1])])
        self.assertEqual(states[1]["reason"], "INCONSISTENT_COUNTERS")

    def test_shoe_change_starts_new_namespace(self):
        tracker = CounterTracker("B06")
        states = run(tracker, [card([60, 30, 25, 5], "10"), card([0, 0, 0, 0], "20"),
                               card([0, 0, 0, 0], "19"), card([0, 0, 0, 0]),
                               card([1, 1, 0, 0]), card([1, 1, 0, 0])])
        self.assertEqual(states[1]["reason"], "SHOE_CHANGE")
        self.assertNotEqual(states[0]["shoe_id"], states[2]["shoe_id"])
        self.assertEqual(confirm(states), [("1", "BANKER")])

    def test_card_identity_and_missing_frames_break_continuity(self):
        tracker = CounterTracker("B06")
        states = run(tracker, [card([5, 2, 2, 1], "10"), card([5, 2, 2, 1], card_id="9999")])
        self.assertEqual(states[1]["reason"], "CARD_IDENTITY_CHANGED")
        tracker = CounterTracker("B06")
        first = run(tracker, [card([5, 2, 2, 1], "10"), card([5, 2, 2, 1])])
        tracker.missing()
        later = run(tracker, [card([6, 3, 2, 1]), card([6, 3, 2, 1])])
        self.assertNotEqual(first[0]["shoe_id"], later[0]["shoe_id"])
        self.assertEqual(confirm(first + later), [])

    def test_unreadable_counters(self):
        tracker = CounterTracker("B06")
        state = tracker.observe({"card_id": "1", "counts": ["?"]}, "2026-11-07T14:00:00+00:00")
        self.assertEqual((state["phase"], state["reason"]), ("UNKNOWN", "COUNTERS_UNREADABLE"))

    def test_lobby_config_defaults(self):
        self.assertEqual(load_lobby_config({}).card_selector, "div.game.isHallGame")

    def test_lobby_config_validation(self):
        self.assertEqual(load_lobby_config({"frame_url_contains": "/hall"}).frame_url_contains, "/hall")
        for bad in ({"table_id_pattern": "[A-Z]+"}, {"unknown": 1}, "x"):
            with self.assertRaises(ValueError, msg=bad):
                load_lobby_config(bad)


class FakeFrame:
    def __init__(self, url, cards):
        self.url, self.cards = url, cards

    async def evaluate(self, script, arg=None):
        return self.cards


class FakePage:
    def __init__(self, frames):
        self.frames = frames

    async def wait_for_timeout(self, ms):
        return None


def lobby_card(card_id, name, counts, countdown="9"):
    return {"card_id": card_id, "name": name, "countdown": countdown, "counts": [str(c) for c in counts]}


class AutoTableReaderTests(unittest.IsolatedAsyncioTestCase):
    def reader(self, folder, tables=()):
        from types import SimpleNamespace
        from agent.adapters.lobby_counters import LobbyCounterReader
        config = SimpleNamespace(source_id="SIM", tables=tables, auto_tables=not tables,
                                 lobby=load_lobby_config({"frame_url_contains": "/hall", "frame_wait_seconds": 0}))
        return LobbyCounterReader(config, folder)

    async def test_discovers_tables_and_handles_absence_and_duplicates(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            reader = self.reader(folder)
            frame = FakeFrame("https://x/egret/hall?params=t", [
                lobby_card("1", "极速百家乐B06", [5, 2, 2, 1]), lobby_card("2", "经典百家乐A36", [9, 4, 4, 1]),
                lobby_card("3", "VIP lounge", [1, 1, 0, 0])])
            first = await reader.capture(FakePage([frame]))
            self.assertEqual(sorted(e["table_id"] for e in first.payload["tables"]), ["A36", "B06"])
            frame.cards = [lobby_card("2", "经典百家乐A36", [9, 4, 4, 1]),
                           lobby_card("7", "极速百家乐B11", [3, 1, 1, 1]), lobby_card("8", "极速百家乐B11", [3, 1, 1, 1])]
            second = await reader.capture(FakePage([frame]))
            # B06 left the view and B11 is ambiguous: both absent from this frame's entries.
            self.assertEqual([e["table_id"] for e in second.payload["tables"]], ["A36"])
            self.assertIn("B06", reader.trackers)
            self.assertIsNone(reader.trackers["B06"].prev)  # continuity dropped while absent

    async def test_fixed_list_ignores_other_tables_and_missing_frame(self):
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            reader = self.reader(folder, tables=(SimpleNamespace(table_id="B06"),))
            frame = FakeFrame("https://x/egret/hall", [lobby_card("1", "极速百家乐B06", [5, 2, 2, 1]),
                                                        lobby_card("2", "经典百家乐A36", [9, 4, 4, 1])])
            captured = await reader.capture(FakePage([frame]))
            self.assertEqual([e["table_id"] for e in captured.payload["tables"]], ["B06"])
            empty = await reader.capture(FakePage([]))
            self.assertFalse(empty.payload["frame_found"])
            self.assertEqual(empty.payload["tables"], [])


if __name__ == "__main__":
    unittest.main()
