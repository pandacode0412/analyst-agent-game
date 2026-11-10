"""Multi-table lobby reader based on published per-shoe counters (evidence level B2).

Each table card shows text counters [total, Banker, Player, Tie, ...] and a
betting countdown. A round is recognized only when total rises by exactly one
and exactly one of Banker/Player/Tie rises by one. Everything else fails closed
as UNKNOWN. Output follows the structured export contract, so the existing
coordinator, validator, gap, and conflict handling apply unchanged.
See docs/05-round-verification.md and docs/17-source-integration.md.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from uuid import uuid4

from ..site_adapter import CapturedFrame

PARSER_VERSION = "lobby_counters/1"
SIDES = ("BANKER", "PLAYER", "TIE")


@dataclass(frozen=True)
class LobbyConfig:
    frame_url_contains: str = ""
    card_selector: str = "div.game.isHallGame"
    name_selector: str = ".table-name"
    countdown_selector: str = ".time"
    counter_selector: str = ".bootReport__count"
    table_id_pattern: str = r"([A-Z]\d+)$"
    frame_wait_seconds: float = 20


def load_lobby_config(block) -> LobbyConfig:
    block = block or {}
    if not isinstance(block, dict):
        raise ValueError("lobby must be an object")
    unknown = set(block) - set(LobbyConfig.__dataclass_fields__)
    if unknown:
        raise ValueError(f"unknown lobby fields: {', '.join(sorted(unknown))}")
    values = {key: (float(value) if key == "frame_wait_seconds" else str(value))
              for key, value in block.items()}
    config = LobbyConfig(**values)
    if re.compile(config.table_id_pattern).groups != 1:
        raise ValueError("table_id_pattern must have exactly one capture group")
    return config


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _namespace(captured_at: str) -> str:
    """A local shoe namespace that never repeats, even for equal timestamps."""
    return f"local-{captured_at}-{uuid4().hex[:8]}"


def parse_counters(raw) -> tuple[int, int, int, int] | None:
    """Return (total, banker, player, tie) when the counters are complete and consistent."""
    try:
        values = [int(str(item).strip()) for item in raw[:4]]
    except (TypeError, ValueError):
        return None
    if len(values) != 4 or min(values) < 0 or values[0] != sum(values[1:]):
        return None
    return values[0], values[1], values[2], values[3]


class CounterTracker:
    """Per-table state machine turning counter snapshots into structured table states."""

    def __init__(self, table_id: str):
        self.table_id = table_id
        self.prev: tuple[int, int, int, int] | None = None
        self.card_id: str | None = None
        self.shoe_ns: str | None = None
        self.result: tuple[int, str] | None = None  # (total, side) still on display

    def missing(self) -> None:
        """The card was not readable this frame: continuity is lost."""
        self.prev, self.card_id, self.shoe_ns, self.result = None, None, None, None

    def _restart(self, counts, card_id, captured_at, reason) -> dict:
        self.prev, self.card_id, self.result = counts, card_id, None
        self.shoe_ns = _namespace(captured_at)
        return {"phase": "UNKNOWN", "reason": reason}

    def observe(self, card: dict, captured_at: str) -> dict:
        counts = parse_counters(card.get("counts", []))
        card_id = str(card.get("card_id") or "")
        betting = bool(re.fullmatch(r"\d+", str(card.get("countdown", "")).strip()))
        if counts is None:
            self.missing()
            return self._state({"phase": "UNKNOWN", "reason": "COUNTERS_UNREADABLE"})
        if self.prev is None:
            self.prev, self.card_id, self.result = counts, card_id, None
            self.shoe_ns = _namespace(captured_at)
            return self._state(self._open(counts, betting))
        if card_id != self.card_id:
            return self._state(self._restart(counts, card_id, captured_at, "CARD_IDENTITY_CHANGED"))
        total, prev_total = counts[0], self.prev[0]
        deltas = [now - old for now, old in zip(counts[1:], self.prev[1:])]
        if total < prev_total:
            return self._state(self._restart(counts, card_id, captured_at, "SHOE_CHANGE"))
        if total == prev_total:
            if any(deltas):
                return self._state(self._restart(counts, card_id, captured_at, "INCONSISTENT_COUNTERS"))
            if betting:
                self.result = None
                return self._state(self._open(counts, True))
            if self.result and self.result[0] == total:
                return self._state(self._settled(counts))
            return self._state(self._open(counts, False))
        if total == prev_total + 1 and sorted(deltas) == [0, 0, 1]:
            self.prev = counts
            self.result = (total, SIDES[deltas.index(1)])
            return self._state(self._settled(counts))
        return self._state(self._restart(counts, card_id, captured_at, "ROUNDS_SKIPPED"))

    def _open(self, counts, betting: bool) -> dict:
        return {"phase": "BETTING" if betting else "DEALING", "round_id": str(counts[0] + 1),
                "final_result": None, "roadmap_revision": ",".join(map(str, counts))}

    def _settled(self, counts) -> dict:
        total, side = self.result
        return {"phase": "RESULT", "round_id": str(total), "final_result": side,
                "roadmap_revision": ",".join(map(str, counts))}

    def _state(self, partial: dict) -> dict:
        entry = {"table_id": self.table_id, "shoe_id": self.shoe_ns or "", "round_id": "",
                 "final_result": None, "roadmap_revision": None}
        entry.update(partial)
        return entry


_READ_CARDS = """(cfg) => [...document.querySelectorAll(cfg.card)].map(card => {
  const text = sel => { const el = card.querySelector(sel); return el ? (el.innerText || '').trim() : ''; };
  return {card_id: card.id || '', name: text(cfg.name), countdown: text(cfg.countdown),
          counts: [...card.querySelectorAll(cfg.counter)].map(el => (el.innerText || '').trim())};
})"""


class LobbyCounterReader:
    """Reads every configured table card from the lobby frame in one evaluation."""

    def __init__(self, config, output_dir: str | Path):
        self.config = config
        self.lobby: LobbyConfig = config.lobby
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.auto_tables = bool(getattr(config, "auto_tables", False))
        self.trackers = {table.table_id: CounterTracker(table.table_id) for table in config.tables}
        self._pattern = re.compile(self.lobby.table_id_pattern)

    def _frame(self, page):
        for frame in page.frames:
            if self.lobby.frame_url_contains in frame.url:
                return frame
        return None

    async def _find_frame(self, page):
        frame = self._frame(page)
        waited = 0.0
        while frame is None and waited < self.lobby.frame_wait_seconds:
            await page.wait_for_timeout(500)
            waited += 0.5
            frame = self._frame(page)
        return frame

    async def capture(self, page) -> CapturedFrame:
        frame_id = uuid4().hex
        frame = await self._find_frame(page)
        cards = []
        if frame is not None:
            cards = await frame.evaluate(_READ_CARDS, {
                "card": self.lobby.card_selector, "name": self.lobby.name_selector,
                "countdown": self.lobby.countdown_selector, "counter": self.lobby.counter_selector})
        captured_at = _utc_now()
        by_table: dict[str, list[dict]] = {}
        for card in cards:
            match = self._pattern.search(card.get("name", ""))
            if match and (self.auto_tables or match.group(1) in self.trackers):
                by_table.setdefault(match.group(1), []).append(card)
        if self.auto_tables:
            # Discovered tables start with a fresh tracker; rounds before discovery are never inferred.
            for table_id in sorted(by_table):
                self.trackers.setdefault(table_id, CounterTracker(table_id))
        entries = []
        manifest = self.output_dir / f"{frame_id}.json"
        for table_id, tracker in self.trackers.items():
            found = by_table.get(table_id, [])
            if len(found) != 1:  # absent or ambiguous: the coordinator records a gap
                tracker.missing()
                continue
            entry = tracker.observe(found[0], captured_at)
            entry["evidence_ref"] = f"{manifest}#{table_id}"
            entries.append(entry)
        # Text-only evidence: the manifest keeps the raw card text; no screenshots are stored.
        payload = {"source_id": self.config.source_id, "frame_id": frame_id,
                   "captured_at_utc": captured_at, "parser_version": PARSER_VERSION,
                   "frame_found": frame is not None, "cards_seen": len(cards),
                   "raw_cards": cards, "tables": entries}
        manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return CapturedFrame(self.config.source_id, frame_id, captured_at, str(manifest), payload=payload)
