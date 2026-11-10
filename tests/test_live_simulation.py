"""End-to-end trial against a local simulated Baccarat page (no real website).

Path under test: login session -> monitor-dom loop -> DOM reader -> coordinator/FSM ->
PostgreSQL -> report-streaks. Requires Chromium and PostgreSQL; data goes to an
isolated temporary schema, never to the real database.
"""
import asyncio
from datetime import timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from uuid import uuid4

STEP_MS = 1000  # each phase step lasts 1 s; one round = BETTING, DEALING, RESULT, RESULT
RESULTS = ["BANKER"] * 13 + ["PLAYER", "TIE", "BANKER"]

LOGIN_HTML = """<html><body><form method="post" action="/login">
<input type="text" name="u"><input type="password" name="p"><button type="submit">login</button>
</form>%s</body></html>"""

LOBBY_HTML = """<html><body>
<div data-table-id="B01" style="width:320px;height:120px;background:#fff">
  <span class="table-name">B01</span> <span class="game-phase"></span>
  <span class="round-id"></span> <span class="shoe-id">S1</span>
  <span class="final-result"></span> <span class="roadmap-revision"></span>
</div>
<script>
// Hold BETTING for 3 s so browser/database warm-up cannot hide the first rounds.
const results = %s, phases = ["BETTING", "DEALING", "RESULT", "RESULT"], t0 = Date.now() + 3000;
function render() {
  const step = Math.max(0, Math.floor((Date.now() - t0) / %d));
  let round = Math.floor(step / 4), phase = phases[step %% 4];
  if (round >= results.length) { round = results.length; phase = "BETTING"; }
  const done = phase === "RESULT";
  const q = s => document.querySelector(s);
  q(".game-phase").innerText = phase;
  q(".round-id").innerText = "R" + (round + 1);
  q(".final-result").innerText = done ? results[round] : "";
  q(".roadmap-revision").innerText = "rev-" + (round + (done ? 1 : 0));
}
render(); setInterval(render, 50);
</script></body></html>"""


LOBBY_TABLES = [
    {"id": "2636", "name": "极速百家乐B06", "seq": ["BANKER"] * 13 + ["PLAYER"]},
    {"id": "2641", "name": "极速百家乐B33",
     "seq": ["PLAYER", "TIE", "BANKER", "PLAYER", "PLAYER", "SHOE", "BANKER", "TIE", "PLAYER"]},
]

ZR_HTML = """<html><body><iframe src="/egret/hall?params=sim-token" width="900" height="400"></iframe></body></html>"""

HALL_HTML = """<html><body><div id="hall"></div>
<script>
const tables = %s, STEP = %d, t0 = Date.now() + 3000, sides = {BANKER: 1, PLAYER: 2, TIE: 3};
for (const t of tables) {
  t.rounds = []; let c = [0, 0, 0, 0];
  for (const item of t.seq) {
    if (item === "SHOE") { c = [0, 0, 0, 0]; continue; }
    const after = c.slice(); after[0] += 1; after[sides[item]] += 1;
    t.rounds.push({before: c, after}); c = after;
  }
  document.getElementById("hall").insertAdjacentHTML("beforeend",
    `<div class="game isHallGame" id="${t.id}"><div class="flex align-center table-name">${t.name}</div>
     <span class="time"></span><span class="status"></span>
     ${[0, 1, 2, 3, 4, 5].map(() => '<div class="bootReport__count"></div>').join('')}
     <div class="bootReport__text">庄</div><div class="bootReport__text">闲</div><div class="bootReport__text">和</div></div>`);
}
function render() {
  const step = Math.max(0, Math.floor((Date.now() - t0) / STEP));
  for (const t of tables) {
    const card = document.getElementById(t.id), r = Math.floor(step / 4), ph = step %% 4;
    let counts, time = "", status = "";
    if (r >= t.rounds.length) { counts = t.rounds[t.rounds.length - 1].after; time = "5"; }
    else if (ph === 0) { counts = t.rounds[r].before; time = String(10 - (step %% 4)); }
    else if (ph === 1) { counts = t.rounds[r].before; status = "开牌中"; }
    else { counts = t.rounds[r].after; status = "结算中"; }
    card.querySelector(".time").innerText = time;
    card.querySelector(".status").innerText = status;
    card.querySelectorAll(".bootReport__count").forEach((el, i) => { el.innerText = String(i < 4 ? counts[i] : 0); });
  }
}
render(); setInterval(render, 50);
</script></body></html>"""


def serve(captcha: bool):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body="", headers=()):
            self.send_response(code)
            for key, value in headers:
                self.send_header(key, value)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def do_GET(self):
            logged_in = "sim_session=ok" in self.headers.get("Cookie", "")
            if self.path.startswith("/zr"):  # like the real site: logged-out visitors land on /home
                if not logged_in:
                    return self._send(302, headers=[("Location", "/home")])
                return self._send(200, ZR_HTML)
            if self.path.startswith("/egret/hall"):
                return self._send(200, HALL_HTML % (json.dumps(LOBBY_TABLES, ensure_ascii=False), STEP_MS))
            if self.path.startswith("/home"):
                return self._send(200, "<html><body><button>登录</button> home</body></html>")
            if self.path.startswith("/lobby"):
                if "sim_session=ok" not in self.headers.get("Cookie", ""):
                    return self._send(302, headers=[("Location", "/login")])
                return self._send(200, LOBBY_HTML % (json.dumps(RESULTS), STEP_MS))
            return self._send(200, LOGIN_HTML % ("<div>SIM_CAPTCHA please verify</div>" if captcha else ""))

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            form = self.rfile.read(length).decode()
            if not captcha and "u=sim-user" in form and "p=sim-pass" in form:
                return self._send(302, headers=[("Set-Cookie", "sim_session=ok; Path=/"),
                                                ("Location", "/lobby")])
            return self._send(302, headers=[("Location", "/login")])

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@unittest.skipUnless(os.getenv("RUN_BROWSER_TESTS") == "1" and os.getenv("RUN_PG_TESTS") == "1",
                     "requires Playwright Chromium and a PostgreSQL test service")
class LiveSimulationTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        self.schema = "sim_" + uuid4().hex
        self.base = os.getenv("DATABASE_URL", "")
        with psycopg.connect(self.base, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.url = f"{self.base} options='-csearch_path={self.schema}'".strip()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        import psycopg
        from psycopg import sql
        self.tmp.cleanup()
        with psycopg.connect(self.base, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def run_monitor(self, captcha: bool, iterations: int, interval: float, lobby: bool = False):
        from agent.browser import monitor_dom_browser
        server = serve(captcha)
        port = server.server_address[1]
        folder = Path(self.tmp.name)
        config = folder / "sim_dom.yaml"
        if lobby:
            config.write_text(f"""
source_id: SIM_LOBBY
reader: lobby_counters
url: http://127.0.0.1:{port}/zr
viewport: {{width: 1000, height: 500}}
ids_reset_per_shoe: true
lobby:
  frame_url_contains: /egret/hall
session:
  storage_state: {folder / 'session_state.json'}
  login_url: http://127.0.0.1:{port}/login
  logged_out_url_fragment: /login
  required_url_fragment: /zr
  captcha_pattern: SIM_CAPTCHA
  relogin_backoff_seconds: 60
tables: auto
""", encoding="utf-8")
        else:
            config.write_text(f"""
source_id: SIM_SOURCE
url: http://127.0.0.1:{port}/lobby
viewport: {{width: 800, height: 400}}
ids_reset_per_shoe: true
session:
  storage_state: {folder / 'session_state.json'}
  login_url: http://127.0.0.1:{port}/login
  logged_out_url_fragment: /login
  captcha_pattern: SIM_CAPTCHA
  relogin_backoff_seconds: 60
tables:
  - id: B01
    selectors: {{root: "[data-table-id='B01']", label: ".table-name", phase: ".game-phase",
                round_id: ".round-id", shoe_id: ".shoe-id", result: ".final-result",
                revision: ".roadmap-revision"}}
""", encoding="utf-8")
        env = {"SITE_USERNAME": "sim-user", "SITE_PASSWORD": "sim-pass"}
        try:
            with mock.patch.dict(os.environ, env):
                asyncio.run(monitor_dom_browser(str(config), self.url, str(folder / "evidence"),
                                                iterations, interval, trusted_round_ids=True))
        finally:
            server.shutdown()
        return folder

    def test_login_monitor_confirm_and_report(self):
        from agent.storage import connect
        from agent.analytics import TZ
        from agent.streak_window import streak_window_data
        rounds_ms = len(RESULTS) * 4 * STEP_MS
        interval = 0.15
        folder = self.run_monitor(captcha=False, iterations=int((rounds_ms + 12000) / 1000 / interval),
                                  interval=interval)
        self.assertTrue((folder / "session_state.json").is_file())
        with connect(self.url) as conn:
            rows = conn.execute("""SELECT round_id, result, finished_at_utc FROM confirmed_rounds
                                   ORDER BY finished_at_utc""").fetchall()
            evidence = conn.execute("SELECT COUNT(*) AS n FROM source_round_evidence").fetchone()["n"]
            # Every simulated round is confirmed exactly once, in order, with evidence.
            gaps = [(row["reason"], row["detected_at_utc"].isoformat()) for row in conn.execute(
                "SELECT reason, detected_at_utc FROM source_gaps ORDER BY detected_at_utc")]
            seen = [(row["round_id"].rsplit(":", 1)[-1], row["result"]) for row in rows]
            self.assertEqual([row["result"] for row in rows], RESULTS, f"rounds={seen} gaps={gaps}")
            self.assertEqual(len({row["round_id"] for row in rows}), len(RESULTS))
            self.assertEqual(evidence, len(RESULTS))
            day = rows[0]["finished_at_utc"].astimezone(TZ).date()
            data = streak_window_data(conn, day, "SIM_SOURCE", "00:00", "24:00")
        self.assertEqual(data["totals"]["reached_13_strict_v1"], {"BANKER": 1, "PLAYER": 0})
        self.assertEqual(data["totals"]["reached_13_tie_transparent_v1"], {"BANKER": 1, "PLAYER": 0})

    def test_lobby_counters_multi_table_with_shoe_change(self):
        from agent.storage import connect
        from agent.analytics import TZ
        from agent.streak_window import streak_window_data
        rounds = max(sum(item != "SHOE" for item in t["seq"]) for t in LOBBY_TABLES)
        interval = 0.15
        self.run_monitor(captcha=False, iterations=int((rounds * 4 * STEP_MS + 15000) / 1000 / interval),
                         interval=interval, lobby=True)
        with connect(self.url) as conn:
            rows = conn.execute("""SELECT table_id, result FROM confirmed_rounds
                                   ORDER BY table_id, finished_at_utc""").fetchall()
            reasons = [row["reason"] for row in conn.execute(
                "SELECT reason FROM source_gaps WHERE table_id = 'B33' ORDER BY detected_at_utc")]
            by_table = {}
            for row in rows:
                by_table.setdefault(row["table_id"], []).append(row["result"])
            self.assertEqual(by_table.get("B06"), ["BANKER"] * 13 + ["PLAYER"], f"gaps={reasons}")
            self.assertEqual(by_table.get("B33"), [item for item in LOBBY_TABLES[1]["seq"] if item != "SHOE"],
                             f"gaps={reasons}")
            self.assertIn("UNKNOWN_PHASE", reasons)  # the shoe change breaks continuity
            day = conn.execute("SELECT MIN(finished_at_utc) AS t FROM confirmed_rounds").fetchone()["t"]
            data = streak_window_data(conn, day.astimezone(TZ).date(), "SIM_LOBBY", "00:00", "24:00")
        self.assertEqual(data["totals"]["reached_13_strict_v1"], {"BANKER": 1, "PLAYER": 0})
        self.assertEqual(data["tables_observed"], 2)

    def test_captcha_blocks_and_records_gap(self):
        from agent.storage import connect
        self.run_monitor(captcha=True, iterations=2, interval=0.5)
        with connect(self.url) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM confirmed_rounds").fetchone()["n"], 0)
            reasons = [row["reason"] for row in conn.execute("SELECT reason FROM source_gaps")]
        self.assertEqual(reasons, ["CAPTCHA_REQUIRED"])


if __name__ == "__main__":
    unittest.main()
