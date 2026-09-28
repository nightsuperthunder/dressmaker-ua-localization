"""Збирає мод: dll + translations/uk.json -> mod/dist, архів mod/DressmakerUA.zip,
і (за бажанням) встановлює в гру.

  python scripts/build_mod.py                   # зібрати
  python scripts/build_mod.py --install         # зібрати і скопіювати в гру (BepInEx має бути встановлений)
  python scripts/build_mod.py --with-bepinex    # покласти в архів BepInEx (для роздачі спільноті)
  python scripts/build_mod.py --mac-bepinex <розпакований BepInEx_macos_universal> --mac-doorstop <розпакований doorstop_macos_release_4.6.0>
                                                # додатково mod/DressmakerUA-macOS.zip

Версія береться з Version у Plugin.cs і записується в uk.json (_meta.version) разом із
_meta.minPlugin (за замовчуванням X.Y.0) — за ними плагін гравця вирішує, чи можна
автоматично взяти текст із нового релізу. Копія для релізу: mod/uk.json (додати до gh release).
Правило: нова остання цифра — лише тексти (оновляться самі); нова перша/друга — новий плагін.
"""
import argparse
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from common import COLLECTIONS, DEFAULT_GAME, STRINGS, TRANSLATIONS, load_json, src_hash

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "mod"
PROJ = MOD / "DressmakerUA"
DIST = MOD / "dist"
DIST_MAC = MOD / "dist_mac"
MAC_EXEC = ("run_bepinex.sh", "install_ua_macos.sh", "libdoorstop.dylib")


def plugin_version():
    m = re.search(r'Version\s*=\s*"([\d.]+)"', (PROJ / "Plugin.cs").read_text(encoding="utf-8"))
    return m.group(1)


def export_json(path, version, min_plugin):
    tr = load_json(TRANSLATIONS)
    out = {"_meta": {"version": version, "minPlugin": min_plugin}}
    out.update({c: {} for c in COLLECTIONS.values()})
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


# Рядки run.sh з Doorstop 4.6.0, які треба змінити (міняємо лише рядки з типовими значеннями)
RUN_SH_EDITS = {
    'executable_name=""': 'executable_name="Dressmaker.app"',
    # BepInEx 5.4.23.5 не може патчити гру в нативному arm64 (BepInEx#1402) — лише через Rosetta
    'archpreference="arm64,x86_64"': 'archpreference="x86_64"',
    'target_assembly="Doorstop.dll"': 'target_assembly="BepInEx/core/BepInEx.Preloader.dll"',
}


def build_mac(bepinex_dir, doorstop_dir):
    """Архів для macOS: BepInEx, плагін, скрипт установки.

    Doorstop 4.5.0 з BepInEx 5.4.23.5 не чіпляється до Unity 6000.3 (UnityDoorstop#108),
    тому libdoorstop.dylib і run.sh беремо з Doorstop 4.6.0 (папка universal/ з doorstop_macos_release).
    """
    if DIST_MAC.exists():
        shutil.rmtree(DIST_MAC)
    shutil.copytree(bepinex_dir, DIST_MAC)
    shutil.copytree(DIST / "BepInEx", DIST_MAC / "BepInEx", dirs_exist_ok=True)
    ds = Path(doorstop_dir)
    shutil.copy2(ds / "universal" / "libdoorstop.dylib", DIST_MAC / "libdoorstop.dylib")
    shutil.copy2(ds / "universal" / ".doorstop_version", DIST_MAC / ".doorstop_version")
    shutil.copy2(ds / "LICENSE", DIST_MAC / "doorstop_LICENSE.txt")
    run = DIST_MAC / "run_bepinex.sh"
    text = (ds / "universal" / "run.sh").read_text(encoding="utf-8")
    lines = text.splitlines()
    for old, new in RUN_SH_EDITS.items():
        if lines.count(old) != 1:
            raise SystemExit(f"run.sh: не знайдено рядок {old!r} — інша версія Doorstop?")
        lines[lines.index(old)] = new
    text = "\n".join(lines) + "\n"
    # read_text перетворює CRLF на LF, write_bytes пише як є: sh на macOS потребує LF
    run.write_bytes(text.encode("utf-8"))
    inst = (MOD / "install_ua_macos.sh").read_text(encoding="utf-8")
    (DIST_MAC / "install_ua_macos.sh").write_bytes(inst.encode("utf-8"))
    shutil.copy2(MOD / "README_UA_macOS.txt", DIST_MAC / "README_UA.txt")
    zip_path = MOD / "DressmakerUA-macOS.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(DIST_MAC.rglob("*")):
            if f.is_dir():
                continue
            zi = zipfile.ZipInfo.from_file(f, f.relative_to(DIST_MAC).as_posix())
            zi.create_system = 3  # Unix: щоб Finder зберіг права на виконання
            zi.external_attr = (0o100755 if f.name in MAC_EXEC else 0o100644) << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, f.read_bytes())
    print(f"Архів для macOS: {zip_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--with-bepinex", help="шлях до розпакованого BepInEx_win_x64 (для архіву спільноти)")
    ap.add_argument("--min-plugin", help="мінімальна версія плагіна для цих текстів (за замовчуванням X.Y.0)")
    ap.add_argument("--mac-bepinex", help="шлях до розпакованого BepInEx_macos_universal (архів для macOS)")
    ap.add_argument("--mac-doorstop", help="шлях до розпакованого doorstop_macos_release_4.6.0 (потрібен з --mac-bepinex)")
    args = ap.parse_args()
    version = plugin_version()
    min_plugin = args.min_plugin or ".".join(version.split(".")[:2] + ["0"])

    subprocess.check_call(["dotnet", "build", "-c", "Release", f"-p:GameDir={args.game}", "-v", "q", "-nologo"],
                          cwd=PROJ)
    if DIST.exists():
        shutil.rmtree(DIST)
    plug = DIST / "BepInEx" / "plugins" / "DressmakerUA"
    plug.mkdir(parents=True)
    shutil.copy2(PROJ / "bin" / "Release" / "DressmakerUA.dll", plug)
    n = export_json(plug / "translations" / "uk.json", version, min_plugin)
    shutil.copy2(plug / "translations" / "uk.json", MOD / "uk.json")
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
    print(f"Перекладених рядків у моді: {n} (версія {version}, minPlugin {min_plugin})")

    zip_path = MOD / "DressmakerUA.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in DIST.rglob("*"):
            z.write(f, f.relative_to(DIST))
    print(f"Архів: {zip_path}")
    if args.mac_bepinex:
        if not args.mac_doorstop:
            raise SystemExit("Для macOS потрібен ще --mac-doorstop (Doorstop 4.6.0, див. build_mac)")
        build_mac(args.mac_bepinex, args.mac_doorstop)

    if args.install:
        game = Path(args.game)
        if not (game / "BepInEx" / "core").exists():
            raise SystemExit("У грі не встановлено BepInEx")
        shutil.copytree(DIST / "BepInEx", game / "BepInEx", dirs_exist_ok=True)
        print(f"Встановлено в {game}")


if __name__ == "__main__":
    main()
