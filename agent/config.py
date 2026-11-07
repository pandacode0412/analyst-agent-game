"""Load explicit per-table bounding boxes from YAML, in raw screenshot pixels."""
from dataclasses import dataclass
from pathlib import Path
import yaml

@dataclass(frozen=True)
class TableRegion:
    table_id: str
    x: int
    y: int
    width: int
    height: int

    def validate(self, image_width: int, image_height: int) -> None:
        if min(self.width, self.height) <= 0 or min(self.x, self.y) < 0:
            raise ValueError(f"Invalid ROI coordinates for {self.table_id}")
        if self.x + self.width > image_width or self.y + self.height > image_height:
            raise ValueError(
                f"ROI {self.table_id} outside screenshot {image_width}x{image_height}; "
                "check browser viewport and config"
            )


def load_regions(filename: str | Path) -> list[TableRegion]:
    with open(filename, encoding="utf-8") as f:
        document = yaml.safe_load(f)
    if not isinstance(document, dict) or not isinstance(document.get("tables"), list):
        raise ValueError("YAML must have a tables: list")
    result: list[TableRegion] = []
    ids: set[str] = set()
    for entry in document["tables"]:
        region = TableRegion(
            table_id=str(entry["id"]).strip(),
            x=int(entry["x"]), y=int(entry["y"]),
            width=int(entry["width"]), height=int(entry["height"]),
        )
        if not region.table_id or region.table_id in ids:
            raise ValueError(f"Duplicate or missing table_id: {region.table_id}")
        ids.add(region.table_id)
        result.append(region)
    if not result:
        raise ValueError("At least one table ROI is required")
    return result
