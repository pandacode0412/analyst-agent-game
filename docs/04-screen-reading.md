# 04 — Reading the screen and calibrating ROIs

## Understand the display

A table video or status panel may show BETTING, DEALING, RESULT, a clock, a final outcome, or a round ID. A roadmap is historical display data. Bead plates, big road, and other roads differ in ordering and in how they show Tie, pairs, and streaks. A colored marker is not always one independent completed round.

config/real_lobby.example.yaml contains approximate roadmap coordinates from an old 1536×864 screenshot. They have not been independently validated.

## ROI coordinates

A Region of Interest is a rectangle (x, y, width, height) measured in screenshot pixels from the upper-left corner. Assign one ROI to each visible table. Avoid dealer video, user names, and balances to reduce noise and exposure of personal data.

## Calibrate an authorized screenshot

1. Choose a fixed viewport, scale factor, and browser zoom.
2. Capture a page you are allowed to view. Mask account details before storing or sharing the image.
3. Measure each table's roadmap rectangle with an image editor.
4. Update config/real_lobby.example.yaml using the table's displayed identity, not its card position.
5. Put the screenshot on the host as assets/my_lobby.png and run:

    docker compose run --rm preview python -m agent.cli preview \
      --image assets/my_lobby.png --config config/real_lobby.example.yaml \
      --out output/my_lobby_roi.png

6. Inspect output/my_lobby_roi.png. Every box must cover the correct table roadmap. Compare highlighted markers with the image, then adjust HSV/contour thresholds only with labeled examples.
7. Keep the masked image and the matching configuration version for reproducibility.

ROI bounds validation alone cannot detect a box that has shifted onto the wrong but still in-bounds card.

## Common visual failure modes

Tie can overlay another marker; pair symbols can share a result color; thin rings can fragment; markers can merge; themes and anti-aliasing alter HSV; a full roadmap can scroll or redraw. Label at least 100 varied images per ROI for marker-level evaluation, then measure false positives and negatives. Accuracy on the synthetic image is not evidence of accuracy on a real site.

## Detecting a new round

One screenshot is a state, not an event. A trusted source round ID and published final result, or a tested phase sequence plus a verified roadmap transition, are required. The prototype can validate pre-extracted TableEvidence but cannot extract these signals from a real page.

## Browser capture

APP_URL defaults to https://example.com. Set only an authorized URL, then run docker compose run --rm capture-browser. To use a specific viewport:

    docker compose run --rm capture-browser python -m agent.cli capture-browser \
      --url https://example.com --width 1536 --height 864 \
      --out output/browser_1536.png

Container Chromium does not see an already-open Windows Chrome window. A login page in the screenshot means this prototype has not obtained a permitted session. Do not bypass login or CAPTCHA.
