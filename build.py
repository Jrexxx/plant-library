#!/usr/bin/env python3
"""
build.py — generates data.json for the Plant Library site.

Reads:
  - ledger.md      (7-column markdown table: ID, Name, Latin, Acquired, Repotted, Pot size, Notes)
  - photos/        (working photos named by plant ID, e.g. 004.jpg, 002_003.jpg, 015_016_017.jpg)
  - id-photos/     (one hero shot per plant, e.g. 057.jpg)

Writes:
  - data.json      (consumed by index.html)

Usage:
    python3 build.py

Photo naming:
  - Filename is one or more zero-padded IDs joined by underscores: 002_003.jpg
  - A photo appears in the gallery of every ID it lists.
  - Capture date is read from EXIF (DateTimeOriginal); galleries sort oldest -> newest.
  - Photos with no EXIF date sort last, by filename.
"""

import json, os, re, sys
from datetime import datetime
from PIL import Image, ExifTags

ROOT = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(ROOT, "ledger.md")
PHOTOS_DIR = os.path.join(ROOT, "photos")
HERO_DIR = os.path.join(ROOT, "id-photos")
OUT = os.path.join(ROOT, "data.json")

# ---- group definitions (ordered) ----
GROUPS = [
    ("Monsteras",              ["006","019","033","056"]),
    ("Pothos",                 ["004","018","023","024","026","027","028","029"]),
    ("Other Aroids",           ["039","060","061","008","012"]),
    ("Calatheas",              ["053","054","055","066","067"]),
    ("Succulents & Cacti",     ["002","003","059","020","065","037","014"]),
    ("Snake & ZZ",             ["034","036","057","058"]),
    ("Palms & Papyrus",        ["015","016","017","041","062","040"]),
    ("Ferns",                  ["045","046","047","048","051"]),
    ("Dracaenas",              ["005","010","021"]),
    ("Tradescantias",          ["009","038","068"]),
    ("Begonias",               ["070","075"]),
    ("Spider Plants",          ["022","042","043","044"]),
    ("Trailing & Undergrowth", ["069","071","072","073","074","049","050","063","064","052","013","032","035","007"]),
    ("Others",                 ["001","011","025","030","031"]),
]

EXIF_DT_TAG = next(k for k, v in ExifTags.TAGS.items() if v == "DateTimeOriginal")
EXIF_DT_DIGITIZED = next(k for k, v in ExifTags.TAGS.items() if v == "DateTimeDigitized")

def clean(s):
    """Strip markdown italics/emphasis and surrounding whitespace."""
    s = s.strip()
    s = re.sub(r'\*([^*]+)\*', r'\1', s)   # *italic*
    return s.strip()

def parse_ledger():
    if not os.path.exists(LEDGER):
        sys.exit(f"ERROR: {LEDGER} not found.")
    plants = {}
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.startswith("| #"):
                continue
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) < 7:
                continue
            pid = cols[0].lstrip("#").strip().zfill(3)
            plants[pid] = {
                "id": pid,
                "name": clean(cols[1]),
                "latin": clean(cols[2]),
                "acquired": clean(cols[3]),
                "repotted": clean(cols[4]),
                "pot": clean(cols[5]),
                "notes": clean(cols[6]),
            }
    return plants

def exif_date(path):
    """Return YYYY-MM-DD string from EXIF, or None."""
    try:
        img = Image.open(path)
        ex = img.getexif()
        # DateTimeOriginal lives in the Exif IFD
        ifd = ex.get_ifd(ExifTags.IFD.Exif) if hasattr(ExifTags, "IFD") else {}
        raw = (ifd.get(EXIF_DT_TAG) or ifd.get(EXIF_DT_DIGITIZED)
               or ex.get(306))  # 306 = DateTime (fallback)
        if not raw:
            return None
        dt = datetime.strptime(str(raw)[:19], "%Y:%m:%d %H:%M:%S")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None

def scan_photos():
    """Map each plant ID -> list of {file, date} sorted oldest->newest."""
    by_id = {}
    if not os.path.isdir(PHOTOS_DIR):
        return by_id
    for fn in os.listdir(PHOTOS_DIR):
        if fn.startswith("."):
            continue
        if not re.search(r'\.(jpe?g|png|webp)$', fn, re.I):
            continue
        stem = re.sub(r'\.(jpe?g|png|webp)$', '', fn, flags=re.I)
        ids = re.findall(r'\d{1,3}', stem)
        if not ids:
            continue
        date = exif_date(os.path.join(PHOTOS_DIR, fn))
        for raw_id in ids:
            pid = raw_id.zfill(3)
            by_id.setdefault(pid, []).append({"file": fn, "date": date})
    # sort each gallery: dated oldest->newest, undated last by filename
    for pid, lst in by_id.items():
        lst.sort(key=lambda p: (p["date"] is None, p["date"] or "", p["file"]))
    return by_id

def find_hero(pid):
    if not os.path.isdir(HERO_DIR):
        return None
    for ext in ("jpg", "jpeg", "png", "webp"):
        cand = f"{pid}.{ext}"
        if os.path.exists(os.path.join(HERO_DIR, cand)):
            return cand
    return None

def main():
    plants = parse_ledger()
    galleries = scan_photos()

    # attach photos + hero to each plant
    for pid, p in plants.items():
        p["hero"] = find_hero(pid)
        p["photos"] = galleries.get(pid, [])

    # coverage check against groups
    grouped = [pid for _, ids in GROUPS for pid in ids]
    gset = set(grouped)
    pset = set(plants)
    orphaned = sorted(pset - gset)
    phantom = sorted(gset - pset)
    dupes = sorted({x for x in grouped if grouped.count(x) > 1})

    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total": len(plants),
        "groups": [{"name": n, "ids": ids} for n, ids in GROUPS],
        "plants": plants,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # report
    photo_count = sum(len(v) for v in galleries.values())
    hero_count = sum(1 for p in plants.values() if p["hero"])
    print(f"✓ data.json written — {len(plants)} plants, {hero_count} heroes, {photo_count} gallery photos")
    if orphaned: print(f"  ⚠ not in any group: {orphaned}")
    if phantom:  print(f"  ⚠ in a group but missing from ledger: {phantom}")
    if dupes:    print(f"  ⚠ in more than one group: {dupes}")
    if not (orphaned or phantom or dupes):
        print("  all plants placed in exactly one group.")

if __name__ == "__main__":
    main()
