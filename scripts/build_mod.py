"""Збирає мод: dll + translations/uk.json -> mod/dist, архів mod/DressmakerUA.zip,
і (за бажанням) встановлює в гру.

  python scripts/build_mod.py                   # зібрати
  python scripts/build_mod.py --install         # зібрати і скопіювати в гру (BepInEx має бути встановлений)
  python scripts/build_mod.py --with-bepinex    # покласти в архів BepInEx (для роздачі спільноті)
"""
import argparse
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from common import COLLECTIONS, DEFAULT_GAME, STRINGS, TRANSLATIONS, load_json, src_hash

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "mod"
PROJ = MOD / "DressmakerUA"
DIST = MOD / "dist"


def export_json(path):
    tr = load_json(TRANSLATIONS)
    out = {c: {} for c in COLLECTIONS.values()}
    strings = load_json(STRINGS)
    if not strings:
        raise SystemExit("Спершу витягніть тексти з гри: python scripts/export_strings.py")
    n = stale = 0
    for s in strings:
        t = tr.get(s["key"])
        if t and t["status"] in ("ok", "manual"):
            out[COLLECTIONS[s["file"]]][str(s["id"])] = t["uk"]
            n += 1
            stale += t.get("src") != src_hash(s["en"])
    if stale:
        print(f"Увага: {stale} перекладів зроблено для старої версії оригіналу (див. review.py export --errors)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--with-bepinex", help="шлях до розпакованого BepInEx_win_x64 (для архіву спільноти)")
    args = ap.parse_args()

    subprocess.check_call(["dotnet", "build", "-c", "Release", f"-p:GameDir={args.game}", "-v", "q", "-nologo"],
                          cwd=PROJ)
    if DIST.exists():
        shutil.rmtree(DIST)
    plug = DIST / "BepInEx" / "plugins" / "DressmakerUA"
    plug.mkdir(parents=True)
    shutil.copy2(PROJ / "bin" / "Release" / "DressmakerUA.dll", plug)
    n = export_json(plug / "translations" / "uk.json")
    (plug / "fonts").mkdir()
    src_fonts = MOD / "fonts"
    if src_fonts.exists():
        for f in src_fonts.iterdir():
            shutil.copy2(f, plug / "fonts")
    if args.with_bepinex:
        shutil.copytree(args.with_bepinex, DIST, dirs_exist_ok=True)
    readme = MOD / "README_UA.txt"
    if readme.exists():
        shutil.copy2(readme, DIST)
    print(f"Перекладених рядків у моді: {n}")

    zip_path = MOD / "DressmakerUA.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in DIST.rglob("*"):
            z.write(f, f.relative_to(DIST))
    print(f"Архів: {zip_path}")

    if args.install:
        game = Path(args.game)
        if not (game / "BepInEx" / "core").exists():
            raise SystemExit("У грі не встановлено BepInEx")
        shutil.copytree(DIST / "BepInEx", game / "BepInEx", dirs_exist_ok=True)
        print(f"Встановлено в {game}")


if __name__ == "__main__":
    main()
