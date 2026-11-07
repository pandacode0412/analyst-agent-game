"""Combine the maintained Markdown chapters into the searchable full guide."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parts = [root / "README.md", *sorted((root / "docs").glob("*.md"))]
output = root / "FULL_DEVELOPER_GUIDE.md"
output.write_text("\n\n---\n\n".join(path.read_text(encoding="utf-8").rstrip() for path in parts) + "\n", encoding="utf-8")
print(f"created {output.name} from {len(parts)} Markdown files")
