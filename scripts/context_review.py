"""Крок 3в. Рецензія перекладу з контекстом сусідніх реплік.

На відміну від proofread.py модель бачить, що було до і після рядка, і не переписує текст,
а показує ЛИШЕ підозрілі місця з поясненням і варіантом виправлення.
Результат — work/context_review.csv у форматі review.py: перегляньте, зайві рядки видаліть,
решту застосуйте командою:  python scripts/review.py import --csv work/context_review.csv

  python scripts/context_review.py                       # усі діалоги
  python scripts/context_review.py --limit 200           # спробувати на шматку
  python scripts/context_review.py --model gemma4:26b-a4b-it-q4_K_M --no-think
  python scripts/context_review.py --gender ...          # лише рід / фемінітиви -> work/gender_review.csv
"""
import argparse
import csv
import difflib
import json
import time
import urllib.error
from pathlib import Path

from common import (GLOSSARY, STRINGS, STYLE, TRANSLATIONS, WORK, load_json, validate,
                    save_json)
from translate import DEFAULT_MODEL, call_raw, glossary_for, ui_terms

REVIEWER = """

ТВОЯ РОЛЬ ЗАРАЗ — РЕДАКТОР-РЕЦЕНЗЕНТ. Тобі дають шматок діалогу: англійський оригінал,
український переклад і сусідні репліки для контексту.

Шукай ЛИШЕ помилки, через які гравець зрозуміє текст інакше, ніж англійською:
- meaning — зміст не відповідає оригіналу: слово чи фразу зрозуміли неправильно;
- gender — неправильний рід, число чи особа («ми обидві» там, де йдеться про жінку й чоловіка;
  «мисливців» там, де в оригіналі жінки; «чоловічий підборіддя» замість «чоловіче»);
- referent — переклад суперечить сусіднім реплікам: не той мовець, не той адресат, не та згадана особа;
- name — власну назву (країна, місто, ім'я) перекладено як звичайне слово або навпаки;
- pun — в оригіналі є жарт чи гра слів, а в перекладі їх немає;
- term — термін не збігається з глосарієм.

СУВОРО ЗАБОРОНЕНО повідомляти про:
- синоніми та інші способи сказати те саме («приїзд» / «прибуття», «заставила» / «змусила»);
- порядок слів, довжину речень, милозвучність;
- пунктуацію та регістр;
- будь-що, де зміст уже переданий правильно.

Кожне зауваження має бути таким, щоб перекладач-людина погодився: «так, це помилка».
Якщо помилок немає — поверни порожній список. Порожній список — нормальна й найчастіша відповідь.

Відповідь — JSON: {"issues": [{"n": номер, "kind": "meaning|gender|referent|name|pun|term",
"why": "що саме не так, коротко", "fix": "виправлений переклад цілком"}]}
Поле "fix" має відрізнятися від наявного перекладу і зберігати теги, плейсхолдери {0} та префікси.
"""

GENDER = """

ТВОЯ РОЛЬ ЗАРАЗ — РЕДАКТОР, ЯКИЙ ПЕРЕВІРЯЄ ЛИШЕ ГРАМАТИЧНИЙ РІД. Тобі дають шматок діалогу:
англійський оригінал, український переклад і сусідні репліки для контексту.

Факти: Кравчиня (the Dressmaker, гравець) — ЖІНКА. Більшість клієнток — жінки. Стать інших
персонажів — з глосарію, коментарів розробників і англійських займенників (she/her, he/him).

Шукай ЛИШЕ такі помилки:
- жінку (зокрема Кравчиню) названо іменником чоловічого роду: художник → художниця, продавець → продавчиня,
  клієнт → клієнтка, друг/друже → подруга/подруго, кравець → кравчиня, співак → співачка, власник → власниця;
- прикметник, дієприкметник чи дієслово минулого часу про жінку стоїть у чоловічому роді
  («я був впевнений» у репліці Кравчині чи іншої жінки → «я була впевнена»; «мій дорогий друже» до Кравчині → «моя дорога подруго»);
- навпаки: чоловіка описано жіночим родом.

СУВОРО ЗАБОРОНЕНО:
- повідомляти про будь-що інше (зміст, стиль, пунктуація, синоніми);
- змінювати рід, якщо з контексту НЕ ясно, хто говорить чи про кого йдеться — тоді мовчи;
- чіпати множину та звертання на «ви» з дієсловами у множині («ви зробили», «ви такі талановиті») — це правильно;
- переробляти репліки чоловіків на жіночий рід.

Якщо помилок немає — поверни порожній список. Це нормальна й найчастіша відповідь.

Відповідь — JSON: {"issues": [{"n": номер, "kind": "gender",
"why": "хто це (жінка/чоловік) і яке слово не того роду", "fix": "виправлений переклад цілком"}]}
У "fix" змінюй лише слова з неправильним родом, решту тексту, теги й плейсхолдери лиши як є.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "kind": {"type": "string",
                             "enum": ["meaning", "gender", "referent", "name", "pun", "term"]},
                    "why": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["n", "why", "fix"],
            },
        }
    },
    "required": ["issues"],
}

COLS = ["key", "file", "status", "en", "uk", "comment", "errors"]


def build(rows, before, after, terms, ui):
    text = " ".join(r["en"] for r in rows)
    parts = []
    g = glossary_for(text, terms) + glossary_for(text, ui)
    if g:
        parts.append("ГЛОСАРІЙ:\n" + "\n".join(g))
    if before:
        parts.append("ЩО БУЛО ПЕРЕД ЦИМ:\n" + "\n".join(
            f"EN: {r['en']}\nUK: {r['uk']}" for r in before))
    if after:
        parts.append("ЩО БУДЕ ПІСЛЯ:\n" + "\n".join(
            f"EN: {r['en']}\nUK: {r['uk']}" for r in after))
    items = []
    for i, r in enumerate(rows, 1):
        head = f"[{i}]" + (f" (коментар розробників: {r['comment']})" if r.get("comment") else "")
        items.append(f"{head}\nEN: {json.dumps(r['en'], ensure_ascii=False)}\n"
                     f"UK: {json.dumps(r['uk'], ensure_ascii=False)}")
    parts.append("ПЕРЕВІР ці рядки:\n\n" + "\n\n".join(items))
    return "\n\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--file", choices=["ui", "tutorial", "content", "dialogue"], action="append")
    ap.add_argument("--limit", type=int, help="скільки рядків перевірити (для проби)")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--tr", default=str(TRANSLATIONS))
    ap.add_argument("--csv")
    ap.add_argument("--items", type=int, default=10, help="рядків у партії")
    ap.add_argument("--before", type=int, default=6, help="скільки реплік контексту перед партією")
    ap.add_argument("--after", type=int, default=3, help="скільки реплік контексту після партії")
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--temp", type=float, default=0.2)
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--only-keys", help="файл зі списком ключів (по одному в рядку) — перевіряти лише їх")
    ap.add_argument("--gender", action="store_true",
                    help="перевіряти лише рід / фемінітиви (вихід work/gender_review.csv)")
    ap.add_argument("--max-words", type=int, default=6,
                    help="--gender: більші правки не застосовуються, лише позначаються")
    ap.add_argument("--restart", action="store_true", help="почати з нуля, забувши попередній прогін")
    args = ap.parse_args()

    strings = load_json(STRINGS)
    tr = load_json(args.tr, {})
    terms = load_json(GLOSSARY)["terms"]
    ui = ui_terms(strings, tr)
    name = "gender_review" if args.gender else "context_review"
    args.csv = args.csv or str(WORK / f"{name}.csv")
    system = STYLE.read_text(encoding="utf-8") + (GENDER if args.gender else REVIEWER)

    state_path = WORK / f"{name}_state.json"
    done = set() if args.restart else set(load_json(state_path, []))
    new_csv = args.restart or not Path(args.csv).exists()

    order = ["ui", "tutorial", "content", "dialogue"]
    files = args.file or ["dialogue"]
    out = open(args.csv, "a" if not new_csv else "w", encoding="utf-8-sig", newline="")
    writer = csv.DictWriter(out, COLS)
    if new_csv:
        writer.writeheader()

    t0, checked, found = time.time(), 0, 0
    for fk in [f for f in order if f in files]:
        rows = []
        for s in sorted((x for x in strings if x["file"] == fk), key=lambda x: x["order"]):
            t = tr.get(s["key"])
            if t and t.get("uk") and t["status"] in ("ok", "manual"):
                rows.append({**s, "uk": t["uk"]})
        todo = rows[args.start:]
        if args.only_keys:
            wanted = set(open(args.only_keys, encoding="utf-8").read().split())
            todo = [r for r in todo if r["key"] in wanted]
        if args.limit:
            todo = todo[:args.limit]
        pos = {r["key"]: i for i, r in enumerate(rows)}
        print(f"\n=== {fk}: перевіряємо {len(todo)} рядків")

        for i in range(0, len(todo), args.items):
            batch = [r for r in todo[i:i + args.items] if r["key"] not in done]
            if not batch:
                continue
            first, last = pos[batch[0]["key"]], pos[batch[-1]["key"]]
            before = rows[max(0, first - args.before):first]
            after = rows[last + 1:last + 1 + args.after]
            try:
                res = call_raw(args, system, build(batch, before, after, terms, ui),
                               args.temp, SCHEMA).get("issues", [])
            except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError) as e:
                print(f"  ! запит не вдався ({e}), пропускаю партію")
                continue
            for data in res:
                n = data.get("n", 0)
                r = batch[n - 1] if 1 <= n <= len(batch) else None
                fix = (data.get("fix") or "").strip()
                if not r or not fix or fix == r["uk"].strip():
                    continue  # без реальної зміни це не зауваження
                why = f"[{data.get('kind', '?')}] {data.get('why', '')}"
                if args.gender:
                    for q1, q2 in ('«»', '""'):
                        if fix[:1] == q1 and fix[-1:] == q2 and r["uk"][:1] != q1:
                            fix = fix[1:-1].strip()
                    if fix == r["uk"].strip():
                        continue
                    # модель любить заодно переписати півречення чи викинути його — таке не приймаємо
                    a, b = r["uk"].split(), fix.split()
                    changed = sum(max(i2 - i1, j2 - j1) for t, i1, i2, j1, j2
                                  in difflib.SequenceMatcher(None, a, b).get_opcodes() if t != "equal")
                    if changed > args.max_words or validate(r["en"], fix):
                        why = f"ПЕРЕВІР ВРУЧНУ (пропозиція моделі: {fix}) {why}"
                        fix = r["uk"]
                writer.writerow({"key": r["key"], "file": r["file"], "status": tr[r["key"]]["status"],
                                 "en": r["en"], "uk": fix, "comment": r["comment"], "errors": why})
                found += 1
            out.flush()
            done.update(r["key"] for r in batch)
            save_json(state_path, sorted(done))
            checked += len(batch)
            el = time.time() - t0
            print(f"  [{fk}] перевірено {checked}, зауважень {found} | {el / 60:.1f} хв", flush=True)

    out.close()
    print(f"\nГотово: перевірено {checked}, зауважень {found} -> {args.csv}")
    print("Перегляньте файл, зайві рядки видаліть, решту застосуйте:")
    print("  python scripts/review.py import --csv " + args.csv)


if __name__ == "__main__":
    main()
