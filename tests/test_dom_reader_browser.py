"""Real Chromium smoke test for the configurable DOM reader."""
import os
import tempfile
import unittest

from agent.adapters.dom import DOMStateReader, load_dom_config
from agent.adapters.structured import StructuredExportAdapter
from pathlib import Path


@unittest.skipUnless(os.getenv("RUN_BROWSER_TESTS") == "1", "requires Playwright Chromium")
class DOMReaderBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_crops_labeled_table_and_blocks_wrong_label(self):
        from playwright.async_api import async_playwright

        config_path = Path(__file__).resolve().parents[1] / "config/real_dom.example.yaml"
        config = load_dom_config(config_path)
        html = """<div data-table-id='B51' style='width:300px;height:150px;background:white'>
            <span class='table-name'>B51</span><span class='game-phase'>RESULT</span>
            <span class='round-id'>R1</span><span class='shoe-id'>S1</span>
            <span class='final-result'>BANKER</span>
            <span class='roadmap-revision'>revision-2</span></div>"""
        with tempfile.TemporaryDirectory() as temporary:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                try:
                    page = await browser.new_page(viewport={"width": config.width,
                                                            "height": config.height})
                    await page.set_content(html)
                    reader = DOMStateReader(config, temporary)
                    frame = await reader.capture(page)
                    self.assertEqual(len(frame.payload["tables"]), 1)
                    self.assertTrue(Path(frame.payload["tables"][0]["evidence_ref"]).is_file())
                    extracted = StructuredExportAdapter(config.source_id).extract(frame)
                    self.assertEqual(extracted[0].evidence.final_result, "BANKER")
                    self.assertFalse(extracted[0].evidence.round_id_trusted)
                    await page.locator(".table-name").evaluate("element => element.textContent = 'B20'")
                    wrong = await reader.capture(page)
                    self.assertEqual(wrong.payload["tables"], [])
                finally:
                    await browser.close()
