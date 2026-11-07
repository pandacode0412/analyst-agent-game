# 11 — Frequently asked questions

**Can a Docker container see my open Windows Chrome window?** No. Playwright starts Chromium inside the container. A normal container cannot capture the Windows desktop merely because Chrome is open there. The prototype can preview a host-provided image or capture an accessible page in its own browser.

**Why do 20 red markers not mean 20 Banker rounds?** Roadmaps can use different layouts, overlays, and scrolling. A static image does not identify which marker is new or whether a round has ended.

**Can machine learning predict the next red or blue result?** Historical patterns can be studied, but this project does not treat them as a reliable betting advantage. It reports descriptive statistics and uncertainty only.

**Why not send every screenshot to a multimodal AI model?** Cost, latency, speed, and auditability can be poor for a fixed UI. First benchmark ROI/CV and use OCR or other models only where labeled evidence shows they are needed.

**Does 100 tables mean 100 Docker containers?** No. Measure permitted browser sessions, rendering behavior, CPU/RAM, capture rate, and coverage before choosing a worker count.

**How can we know rounds were not missed?** A trustworthy source sequence/ID, heartbeat, timestamps, gap detection, and comparison with independently labeled data help. Without a comparison source, coverage is uncertain; do not claim 100%.

**Which database does the agent use?** PostgreSQL 17 is the default. The old SQLite file is used only by the one-time, read-only migration tool. A database upgrade does not make screenshot interpretations trustworthy.

**Why schedule a report if the agent runs continuously?** Observation and daily report generation are different jobs. The report job gathers already verified historical data.

**Can the agent include other players' stakes?** Only if a permitted source explicitly provides accurate, defined stake data. Roadmap colors cannot reveal total stakes.

**Can an official export replace OCR?** Yes, if the provider authorizes it. A documented export may be a stronger source of round identity and final results than screen parsing.

**Which files enable automatic confirmation?** An approved adapter produces TableEvidence under agent/site_adapter.py's contract. agent/coordinator.py runs the conservative pipeline and agent/live_store.py persists validated candidates, evidence, gaps, and conflicts. The structured export and configurable DOM adapters provide input formats; the shipped DOM selectors have not been validated against a named website. Enable the trusted-ID gate only after a held-out source review.
