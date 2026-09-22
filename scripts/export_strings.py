"""Крок 1. Витягує англійські рядки гри в work/strings.json.

Оригінальні тексти гри НЕ зберігаються в репозиторії — кожен дістає їх зі своєї копії гри:

  python scripts/export_strings.py                          # з гри за шляхом за замовчуванням
  python scripts/export_strings.py --game "D:\\Steam\\steamapps\\common\\Dressmaker"
  python scripts/export_strings.py --yaml                   # з YAML-експорту (ui.yaml тощо в корені проєкту)

Потрібно: pip install UnityPy pyyaml
"""
import argparse
import sys
from pathlib import Path

from common import (BUNDLE_DIR, COLLECTIONS, DEFAULT_GAME, EN_BUNDLE, FILES,
                    ROOT, STRINGS, WORK, load_unity_yaml, save_json)


def rows_from_table(key, mb):
    """mb — словник StringTable (з YAML або з бандла, структура однакова)."""
    comments = {}
    for ref in (mb.get("references") or {}).get("RefIds") or []:
        text = (ref.get("data") or {}).get("m_CommentText")
        if text:
            comments[ref["rid"]] = text
    out = []
    for i, row in enumerate(mb["m_TableData"]):
        en = row.get("m_Localized")
        en = "" if en is None else str(en)
        rids = [it["rid"] for it in (row.get("m_Metadata") or {}).get("m_Items") or []]
        out.append({
            "key": f"{key}:{row['m_Id']}",
            "file": key,
            "id": row["m_Id"],
            "order": i,
            "en": en,
            "comment": " | ".join(comments[r] for r in rids if r in comments),
        })
    return out


def from_game(game_dir):
    try:
        import UnityPy
    except ImportError:
        sys.exit("Потрібен UnityPy: pip install UnityPy")
    bundle = Path(game_dir) / BUNDLE_DIR / EN_BUNDLE
    if not bundle.exists():
        sys.exit(f"Не знайдено {bundle}\nВкажіть папку гри: --game \"...\\Dressmaker\"")
    env = UnityPy.load(str(bundle))
    tables = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        t = obj.read_typetree()
        if "m_TableData" in t:
            tables[t["m_Name"]] = t
    out = []
    for key, coll in COLLECTIONS.items():
        name = f"{coll}_en"
        if name not in tables:
            sys.exit(f"У бандлі немає таблиці {name}")
        rows = rows_from_table(key, tables[name])
        print(f"{name}: {len(rows)} рядків")
        out += rows
    return out


def from_yaml():
    out = []
    for key, fname in FILES.items():
        rows = rows_from_table(key, load_unity_yaml(ROOT / fname))
        print(f"{fname}: {len(rows)} рядків")
        out += rows
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=DEFAULT_GAME, help="папка гри Dressmaker")
    ap.add_argument("--yaml", action="store_true", help="читати з YAML-файлів у корені проєкту")
    args = ap.parse_args()

    WORK.mkdir(exist_ok=True)
    out = from_yaml() if args.yaml else from_game(args.game)
    save_json(STRINGS, out)
    print(f"Разом {len(out)} -> {STRINGS}")


if __name__ == "__main__":
    main()
