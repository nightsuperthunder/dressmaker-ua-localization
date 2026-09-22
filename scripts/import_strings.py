"""Крок 5. Записує переклад у копії YAML-файлів гри в папку out/.

  python scripts/import_strings.py                 # замінює англійський текст (m_Code лишається en)
  python scripts/import_strings.py --locale uk     # ще й міняє m_Code/m_Name на uk (для окремої локалі)
  python scripts/import_strings.py --allow-missing # неперекладене лишиться англійською

Форматування файлу зберігається; змінюються лише значення m_Localized.
Необов'язковий крок (мод цього не потребує). Потрібні YAML-експорти таблиць гри (ui.yaml, tutoriarl.yaml,
content.yaml, dialoge.yaml) у корені проєкту — їх можна отримати з гри через AssetRipper/UABEA.
"""
import argparse
import json
import re
import sys

from common import (FILES, OUT, ROOT, STRINGS, TRANSLATIONS, load_json,
                    load_unity_yaml)

ID_RE = re.compile(r"^  - m_Id: (-?\d+)\s*$")
LOC_RE = re.compile(r"^    m_Localized:")
META_RE = re.compile(r"^    m_Metadata:")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tr", default=str(TRANSLATIONS))
    ap.add_argument("--locale", help="напр. uk — змінити m_Code і суфікс m_Name")
    ap.add_argument("--allow-missing", action="store_true")
    args = ap.parse_args()

    tr = load_json(args.tr, {})
    strings = load_json(STRINGS)
    missing = [s["key"] for s in strings
               if s["key"] not in tr or tr[s["key"]]["status"] not in ("ok", "manual", "skip")]
    if missing and not args.allow_missing:
        sys.exit(f"{len(missing)} рядків без готового перекладу (напр. {missing[:3]}). "
                 f"Доперекладай або запусти з --allow-missing.")

    absent = [f for f in FILES.values() if not (ROOT / f).exists()]
    if absent:
        sys.exit(f"Немає YAML-файлів гри: {absent}. Цей крок необов'язковий — для мода використовуйте build_mod.py.")
    OUT.mkdir(exist_ok=True)
    for fk, fname in FILES.items():
        with open(ROOT / fname, encoding="utf-8", newline="") as f:
            raw = f.read()
        nl = "\r\n" if "\r\n" in raw else "\n"
        lines = raw.split(nl)
        res, cur_id, i, replaced = [], None, 0, 0
        while i < len(lines):
            line = lines[i]
            m = ID_RE.match(line)
            if m:
                cur_id = m.group(1)
            if cur_id is not None and LOC_RE.match(line):
                # значення може займати кілька рядків — до m_Metadata
                j = i + 1
                while j < len(lines) and not META_RE.match(lines[j]):
                    j += 1
                t = tr.get(f"{fk}:{cur_id}")
                if t and t["status"] in ("ok", "manual"):
                    res.append("    m_Localized: " + json.dumps(t["uk"], ensure_ascii=False))
                    replaced += 1
                else:
                    res.extend(lines[i:j])
                cur_id = None
                i = j
                continue
            if args.locale:
                line = re.sub(r"^(    m_Code: )en\s*$", rf"\g<1>{args.locale}", line)
                line = re.sub(r"^(  m_Name: \w+_)en\s*$", rf"\g<1>{args.locale}", line)
            res.append(line)
            i += 1
        dst = OUT / fname
        with open(dst, "w", encoding="utf-8", newline="") as f:
            f.write(nl.join(res))

        # контроль: перечитуємо і порівнюємо
        mb = load_unity_yaml(dst)
        errs = 0
        for row in mb["m_TableData"]:
            t = tr.get(f"{fk}:{row['m_Id']}")
            if t and t["status"] in ("ok", "manual") and str(row["m_Localized"]) != t["uk"]:
                errs += 1
        print(f"{fname}: замінено {replaced}, помилок перевірки {errs} -> {dst}")


if __name__ == "__main__":
    main()
