"""Detect circular colored ROADMAP MARKERS in configured ROIs.

IMPORTANT: marker counts are NOT number of rounds. A single round may change
roadmap position, redraw the board, or place a tie overlay on an existing marker.
"""
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np
from .config import TableRegion

@dataclass
class Marker:
    color: str
    cx: int
    cy: int
    radius: int


def load_image(path: str | Path) -> np.ndarray:
    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if frame is None:
        raise FileNotFoundError(f"Cannot read image: {path}")
    return frame


def _color_mask(hsv: np.ndarray, color: str) -> np.ndarray:
    if color == "RED":
        lo = cv2.inRange(hsv, np.array([0, 65, 55]), np.array([14, 255, 255]))
        hi = cv2.inRange(hsv, np.array([165, 65, 55]), np.array([179, 255, 255]))
        return cv2.bitwise_or(lo, hi)
    if color == "BLUE":
        return cv2.inRange(hsv, np.array([88, 60, 60]), np.array([133, 255, 255]))
    raise ValueError(color)


def detect_markers(roi: np.ndarray, min_area: int = 9, max_area: int = 350) -> list[Marker]:
    """Find ring/filled markers; heuristic, MUST be calibrated on real images."""
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    found: list[Marker] = []
    for color in ("RED", "BLUE"):
        mask = _color_mask(hsv, color)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            if not min_area <= area <= max_area:
                continue
            (cx, cy), radius = cv2.minEnclosingCircle(c)
            perimeter = cv2.arcLength(c, True)
            if radius < 2 or perimeter == 0:
                continue
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            if circularity < 0.22:  # thin ring-like icons have low contour circularity
                continue
            found.append(Marker(color, int(cx), int(cy), max(2, int(radius))))
    return found


def analyze_frame(frame: np.ndarray, regions: list[TableRegion]) -> tuple[np.ndarray, list[dict]]:
    canvas = frame.copy()
    summaries: list[dict] = []
    h, w = frame.shape[:2]
    for region in regions:
        region.validate(w, h)
        crop = frame[region.y: region.y + region.height, region.x: region.x + region.width]
        markers = detect_markers(crop)
        red = sum(m.color == "RED" for m in markers)
        blue = sum(m.color == "BLUE" for m in markers)
        cv2.rectangle(canvas, (region.x, region.y),
                      (region.x + region.width, region.y + region.height), (0, 220, 255), 2)
        label_y = max(18, region.y - 6)
        cv2.putText(canvas, f"{region.table_id} markers R:{red} B:{blue}",
                    (region.x, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.46,
                    (250, 250, 250), 2, cv2.LINE_AA)
        cv2.putText(canvas, f"{region.table_id} markers R:{red} B:{blue}",
                    (region.x, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.46,
                    (30, 30, 30), 1, cv2.LINE_AA)
        for m in markers:
            center = (region.x + m.cx, region.y + m.cy)
            cv2.circle(canvas, center, m.radius + 1, (0, 255, 255), 1)
        summaries.append({"table_id": region.table_id, "red_markers": red,
                          "blue_markers": blue, "status": "OBSERVED_NOT_CONFIRMED"})
    return canvas, summaries
