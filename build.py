#!/usr/bin/env python3
"""Build Kodi add-on zips and the repository index into docs/ (served by GitHub Pages).

Usage: python3 build.py

For every add-on folder listed in ADDONS it creates:
  docs/<id>/<id>-<version>.zip   (what the Kodi repository downloads)
and then writes docs/addons.xml, docs/addons.xml.md5 and docs/index.html.
The repository zip is also copied to docs/ root so it can be installed
with "Install from zip file" straight from the Pages URL.
"""
import hashlib
import html
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
ADDONS = ["repository.sc", "skin.sc.estuary"]
REPO_ID = "repository.sc"
SKIP_NAMES = {".git", ".DS_Store", "__pycache__", "Thumbs.db"}


def read_addon(folder: Path) -> tuple[str, str, str]:
    """Return (id, version, addon.xml text without the XML declaration)."""
    text = (folder / "addon.xml").read_text(encoding="utf-8")
    root = ET.fromstring(text)
    body = text[text.index("<addon"):].strip()
    return root.get("id"), root.get("version"), body


def build_zip(folder: Path, addon_id: str, version: str) -> Path:
    out_dir = DOCS / addon_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    zip_path = out_dir / f"{addon_id}-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            rel = path.relative_to(folder)
            if any(part in SKIP_NAMES for part in rel.parts) or path.is_dir():
                continue
            zf.write(path, Path(addon_id) / rel)
    # Kodi shows these next to the add-on in the repository browser
    for asset in ("icon.png", "resources/icon.png", "resources/fanart.jpg"):
        src = folder / asset
        if src.exists():
            shutil.copy2(src, out_dir / Path(asset).name)
    return zip_path


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    bodies, links = [], []
    for name in ADDONS:
        addon_id, version, body = read_addon(ROOT / name)
        zip_path = build_zip(ROOT / name, addon_id, version)
        bodies.append(body)
        print(f"built {zip_path.relative_to(ROOT)} ({zip_path.stat().st_size // 1024} KB)")
        if addon_id == REPO_ID:
            root_copy = DOCS / zip_path.name
            for old in DOCS.glob(f"{REPO_ID}-*.zip"):
                old.unlink()
            shutil.copy2(zip_path, root_copy)
            links.append(root_copy.name)

    addons_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n'
        + "\n".join(bodies)
        + "\n</addons>\n"
    )
    (DOCS / "addons.xml").write_text(addons_xml, encoding="utf-8")
    md5 = hashlib.md5(addons_xml.encode("utf-8")).hexdigest()
    (DOCS / "addons.xml.md5").write_text(md5, encoding="utf-8")

    # Kodi's "Add source" reads plain <a href> links from this page
    items = "\n".join(f'<a href="{html.escape(n)}">{html.escape(n)}</a><br>' for n in links)
    (DOCS / "index.html").write_text(
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\"><title>SC Repository</title></head>\n"
        f"<body>\n{items}\n</body></html>\n",
        encoding="utf-8",
    )
    (DOCS / ".nojekyll").touch()
    print("wrote docs/addons.xml, addons.xml.md5, index.html")


if __name__ == "__main__":
    main()
