"""Generate a fake, privacy-safe lobby screenshot for CV calibration and teaching."""
from pathlib import Path
import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/synthetic_lobby.png"
CONF = ROOT / "config/synthetic_tables.yaml"


def main():
    frame = np.full((720, 1280, 3), (26, 32, 42), dtype=np.uint8)
    cv2.putText(frame, "SYNTHETIC BACCARAT LOBBY - TEST DATA ONLY", (45, 52),
                cv2.FONT_HERSHEY_SIMPLEX, 0.95, (240, 240, 240), 2, cv2.LINE_AA)
    tables = ["B51", "B20", "B07", "J49", "U12", "B14"]
    cfg = {"tables": []}
    for idx, name in enumerate(tables):
        col, row = idx % 3, idx // 3
        x = 40 + 410 * col
        y = 95 + 290 * row
        cv2.rectangle(frame, (x, y), (x + 372, y + 255), (40, 49, 64), -1)
        cv2.rectangle(frame, (x, y), (x + 372, y + 255), (93, 109, 128), 2)
        cv2.putText(frame, f"TABLE {name}", (x+16, y+35), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (235, 235, 235), 2, cv2.LINE_AA)
        cv2.rectangle(frame, (x+14, y+50), (x+358, y+111), (28, 83, 96), -1)
        cv2.putText(frame, "Demo video area", (x+22, y+86), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (220, 223, 229), 1)
        roadx, roady, roadw, roadh = x+14, y+130, 344, 105
        cv2.rectangle(frame, (roadx, roady), (roadx+roadw, roady+roadh), (16,22,30), -1)
        cfg["tables"].append({"id":name, "x":roadx,"y":roady,"width":roadw,"height":roadh})
        for j in range(20 + idx):
            c = j % 14
            r = (j // 14 + (j // 5) % 3) % 5
            pos = roadx + 14 + c*22, roady + 13 + r*19
            color = (52, 75, 223) if ((j+idx)%3 != 0) else (227, 124, 42)
            cv2.circle(frame, pos, 7, color, 2)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    CONF.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT), frame)
    CONF.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(OUT)
    print(CONF)

if __name__ == "__main__":
    main()
