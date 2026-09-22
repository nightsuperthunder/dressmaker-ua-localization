"""Крок 3б. Вичитка перекладу локальною моделлю (редактор).

Модель отримує оригінал + переклад і виправляє граматику, рід, кальки, відповідність глосарію.
Попередня версія зберігається в полі uk_before_proof; всі зміни пишуться в work/proofread_log.csv.
Ручні правки (manual) не чіпаються. Можна переривати і запускати знову.

  python scripts/proofread.py
  python scripts/proofread.py --file dialogue --limit 30   # тест
  python scripts/proofread.py --revert                     # відкотити вичитку
"""
import argparse
import csv
import json
import sys
import time
import urllib.error

from common import (GLOSSARY, STRINGS, STYLE, TRANSLATIONS, WORK, load_json,
                    save_json, validate)
from translate import (DEFAULT_MODEL, FILE_HINTS, call_ollama, glossary_for,
                       make_batches, ui_terms)

EDITOR = """

ТВОЯ РОЛЬ ЗАРАЗ — РЕДАКТОР. Тобі дають англійський оригінал і готовий український переклад.
Виправ у перекладі:
- граматичні помилки, узгодження роду/числа/відмінка;
- кальки з англійської й неприродні звороти (див. СТИЛЬ);
- смислові помилки й пропуски порівняно з оригіналом;
- невідповідність глосарію та назвам інтерфейсу.
Якщо переклад уже добрий — поверни його БЕЗ ЗМІН. Не переписуй заради переписування,
не додавай нічого від себе. Усі ТЕХНІЧНІ ПРАВИЛА (теги, плейсхолдери, префікси, \\:) лишаються в силі.
"""


def build(batch, fk, terms, ui):
    text = " ".join(x["en"] for x in batch)
    parts = [FILE_HINTS[fk]]
    g = glossary_for(text, terms)
    if g:
        parts.append("ГЛОСАРІЙ:\n" + "\n".join(g))
    u = glossary_for(text, ui)
    if u:
        parts.append("НАПИСИ ІНТЕРФЕЙСУ (у лапках «…», не відмінювати):\n" + "\n".join(u))
    items = []
    for i, x in enumerate(batch, 1):
        head = f"[{i}]" + (f" (коментар розробників: {x['comment']})" if x.get("comment") else "")
        items.append(f"{head}\nEN: {json.dumps(x['en'], ensure_ascii=False)}\n"
                     f"UK: {json.dumps(x['uk'], ensure_ascii=False)}")
    parts.append(f"ВІДРЕДАГУЙ ці {len(batch)} перекладів. Відповідь — JSON {{\"t\": [{{\"n\": номер, "
                 f"\"uk\": \"виправлений або незмінний переклад\"}}]}} з рівно {len(batch)} елементами.\n\n"
                 + "\n\n".join(items))
    return "\n\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--file", choices=["ui", "tutorial", "content", "dialogue"], action="append")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--tr", default=str(TRANSLATIONS))
    ap.add_argument("--chars", type=int, default=1500)
    ap.add_argument("--items", type=int, default=15)
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--temp", type=float, default=0.2)
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    strings = load_json(STRINGS)
    tr = load_json(args.tr, {})

    if args.revert:
        n = 0
        for v in tr.values():
            if "uk_before_proof" in v:
                v["uk"] = v.pop("uk_before_proof")
                v.pop("proofed", None)
                n += 1
        save_json(args.tr, tr)
        print(f"Відкочено {n}")
        return

    terms = load_json(GLOSSARY)["terms"]
    allowed = {t["en"] for t in terms}
    system = STYLE.read_text(encoding="utf-8") + EDITOR
    ui = ui_terms(strings, tr)
    log_path = WORK / "proofread_log.csv"
    new_log = not log_path.exists()
    log = open(log_path, "a", encoding="utf-8-sig", newline="")
    lw = csv.writer(log)
    if new_log:
        lw.writerow(["key", "en", "before", "after"])

    order = ["ui", "tutorial", "content", "dialogue"]
    files = args.file or order
    t0, done, changed = time.time(), 0, 0
    for fk in [f for f in order if f in files]:
        rows = []
        for s in sorted((x for x in strings if x["file"] == fk), key=lambda x: x["order"]):
            t = tr.get(s["key"])
            if t and t["status"] == "ok" and not t.get("proofed") and t.get("model") != "dup":
                rows.append({**s, "uk": t["uk"]})
        if args.limit:
            rows = rows[:args.limit]
        print(f"\n=== {fk}: на вичитку {len(rows)}")
        for batch in make_batches(rows, args.chars, args.items):
            try:
                res = call_ollama(args, system, build(batch, fk, terms, ui), args.temp)
            except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError) as e:
                print(f"  ! запит не вдався ({e}), пропускаю партію")
                continue
            bc = 0
            for i, r in enumerate(batch, 1):
                t = tr[r["key"]]
                new = res.get(i)
                t["proofed"] = True
                if new and new != r["uk"] and not validate(r["en"], new, allowed):
                    t["uk_before_proof"] = r["uk"]
                    t["uk"] = new
                    lw.writerow([r["key"], r["en"], r["uk"], new])
                    bc += 1
            save_json(args.tr, tr)
            log.flush()
            done += len(batch)
            changed += bc
            el = time.time() - t0
            print(f"  [{fk}] +{len(batch)} (змінено {bc}) | всього {done}, змінено {changed} | "
                  f"{el / 60:.1f} хв")
    log.close()
    print(f"\nВичитку завершено: переглянуто {done}, змінено {changed}. Лог: {log_path}")


if __name__ == "__main__":
    main()
