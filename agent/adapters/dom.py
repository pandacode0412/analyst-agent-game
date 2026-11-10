"""Configurable DOM reader for authorized pages exposing explicit round state.

Selectors are placeholders until validated against one actual source and layout.
Canvas-only or iframe-only games need a different source-specific reader.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import yaml

from ..session import SessionConfig, load_session_config
from .lobby_counters import LobbyConfig, load_lobby_config
from ..run_settings import RunConfig, load_run_config
from ..site_adapter import CapturedFrame


FIELDS = ("root", "label", "phase", "round_id", "result", "revision")


@dataclass(frozen=True)
class DOMTable:
    table_id: str
    selectors: dict[str, str]


@dataclass(frozen=True)
class DOMConfig:
    source_id: str
    url: str
    width: int
    height: int
    tables: tuple[DOMTable, ...]
    phase_map: dict[str, str]
    result_map: dict[str, str]
    ids_reset_per_shoe: bool
    session: SessionConfig | None = None
    reader: str = "dom"
    lobby: LobbyConfig | None = None
    run: RunConfig = RunConfig()
    auto_tables: bool = False


def load_dom_config(path: str | Path) -> DOMConfig:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("DOM config must be an object")
    source_id = str(document.get("source_id", "")).strip()
    url = str(document.get("url", "")).strip()
    viewport = document.get("viewport", {})
    entries = document.get("tables", [])
    if not source_id or not url.startswith(("https://", "http://")):
        raise ValueError("source_id and an HTTP(S) URL are required")
    reader = str(document.get("reader", "dom")).strip()
    auto_tables = entries == "auto"
    if auto_tables and reader != "lobby_counters":
        raise ValueError("tables: auto requires reader: lobby_counters")
    if auto_tables:
        entries = []
    if not isinstance(viewport, dict) or not isinstance(entries, list) or not (entries or auto_tables):
        raise ValueError("viewport and a nonempty tables list (or tables: auto) are required")
    width, height = int(viewport.get("width", 0)), int(viewport.get("height", 0))
    if width <= 0 or height <= 0:
        raise ValueError("viewport width and height must be positive")
    if reader not in ("dom", "lobby_counters"):
        raise ValueError("reader must be dom or lobby_counters")
    tables = []
    ids = set()
    for entry in entries:
        table_id = str(entry.get("id", "")).strip()
        selectors = entry.get("selectors", {})
        if not table_id or table_id in ids or not isinstance(selectors, dict):
            raise ValueError("table IDs must be unique and selectors must be an object")
        if reader == "dom" and any(not isinstance(selectors.get(field), str) or not selectors[field].strip()
               for field in FIELDS):
            raise ValueError(f"table {table_id} needs selectors for {', '.join(FIELDS)}")
        ids.add(table_id)
        tables.append(DOMTable(table_id, selectors))
    phase_map = {str(k).strip().upper(): str(v).strip().upper()
                 for k, v in (document.get("phase_map") or {}).items()}
    result_map = {str(k).strip().upper(): str(v).strip().upper()
                  for k, v in (document.get("result_map") or {}).items()}
    if any(value not in ("BETTING", "DEALING", "RESULT", "UNKNOWN")
           for value in phase_map.values()):
        raise ValueError("phase_map values must be canonical phases")
    if any(value not in ("BANKER", "PLAYER", "TIE") for value in result_map.values()):
        raise ValueError("result_map values must be canonical outcomes")
    return DOMConfig(source_id, url, width, height, tuple(tables), phase_map,
                     result_map, bool(document.get("ids_reset_per_shoe", True)),
                     load_session_config(document.get("session")), reader,
                     load_lobby_config(document.get("lobby")) if reader == "lobby_counters" else None,
                     load_run_config(document.get("run")), auto_tables)


class DOMStateReader:
    def __init__(self, config: DOMConfig, output_dir: str | Path):
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def capture(self, page) -> CapturedFrame:
        frame_id = uuid4().hex
        captured_at = datetime.now(timezone.utc).isoformat()
        entries = []
        for table in self.config.tables:
            root = page.locator(table.selectors["root"])
            if await root.count() != 1:
                continue
            try:
                # Read the visible fields in one browser execution turn so a
                # phase transition cannot mix text from several UI moments.
                fields = await root.evaluate("""(node, selectors) => {
                    const read = key => {
                        const selector = selectors[key];
                        const target = selector ? node.querySelector(selector) : null;
                        return target ? (target.innerText || '').trim() : '';
                    };
                    return {
                        label: read('label'), phase: read('phase'),
                        round_id: read('round_id'), shoe_id: read('shoe_id'),
                        result: read('result'), revision: read('revision')
                    };
                }""", table.selectors, timeout=1500)
                label = fields["label"]
                if label != table.table_id:
                    continue
                phase_raw = fields["phase"].upper()
                result_raw = fields["result"].upper()
                table_path = self.output_dir / f"{frame_id}_{len(entries):02d}.png"
                await root.screenshot(path=str(table_path), timeout=3000)
                entries.append({
                    "table_id": table.table_id,
                    "phase": self.config.phase_map.get(phase_raw, phase_raw or "UNKNOWN"),
                    "round_id": fields["round_id"],
                    "shoe_id": fields["shoe_id"],
                    "final_result": self.config.result_map.get(result_raw, result_raw or None),
                    "roadmap_revision": fields["revision"],
                    "evidence_ref": str(table_path),
                })
            except Exception:
                # Coordinator records a gap for an omitted or unreadable table.
                continue
        payload = {"source_id": self.config.source_id, "frame_id": frame_id,
                   "captured_at_utc": captured_at, "tables": entries}
        manifest = self.output_dir / f"{frame_id}.json"
        manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return CapturedFrame(self.config.source_id, frame_id, captured_at,
                             str(manifest), payload=payload)
