"""Крок 3. Перекладає рядки через локальну модель в Ollama.

Приклади:
  # тест: 40 діалогових рядків в окремий файл
  python scripts/translate.py --file dialogue --limit 40 --out work/test_mamay.json

  # повний переклад (можна переривати Ctrl+C і запускати знову — продовжить з місця)
  python scripts/translate.py

  # перекласти заново лише рядки з помилками
  python scripts/translate.py --redo-errors
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request

from common import (GLOSSARY, STRINGS, STYLE, TRANSLATIONS, load_json,
                    save_json, src_hash, validate)

DEFAULT_MODEL = "hf.co/INSAIT-Institute/MamayLM-Gemma-3-12B-IT-v2.0-GGUF:Q8_0"
OLLAMA = "http://localhost:11434/api/chat"

FILE_HINTS = {
    "ui": "Це написи інтерфейсу гри (кнопки, меню, повідомлення). Коротко і зрозуміло.",
    "tutorial": "Це підказки навчання (туторіалу): як користуватися редактором суконь. Чітко і дружньо, "
                "природною українською, як у якісно локалізованих іграх (без кальок на кшталт "
                "«деякі», «давайте», «ми розблокували»).",
    "content": "Це назви тканин, деталей одягу, аксесуарів та їхні описи з каталогу гри. "
               "Назви — у називному відмінку з великої літери; описи — повні речення.",
    "dialogue": "Це діалоги персонажів та статті світської хроніки. Рядки йдуть підряд, "
                "зберігай зв'язність і характер мовців.",
}

# Слова, які гра підставляє в {0}/{1} речень
COLOURS = {"Blue", "Green", "Pink", "Purple", "Red", "Yellow", "Orange", "Black",
           "White", "Grey", "Brown"}
FABRICS = {"Cotton", "Lace", "Linen", "Silk", "Velvet", "Wool"}
EXTRA_NOTES = {
    **{c: "Колір, який гра підставляє в речення перед словом «колір». Переклади одним "
          "прикметником чоловічого роду в називному відмінку, з великої літери (напр. «Синій»)."
       for c in COLOURS},
    **{f: "Тип тканини, який гра підставляє в речення. Переклади одним іменником у "
          "називному відмінку з великої літери (напр. «Шовк»)."
       for f in FABRICS},
}

SCHEMA = {
    "type": "object",
    "properties": {
        "t": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"n": {"type": "integer"}, "uk": {"type": "string"}},
                "required": ["n", "uk"],
            },
        }
    },
    "required": ["t"],
}


def is_stub(en):
    return re.fullmatch(r"Stub( response| reply| excelled text)?", en.strip()) is not None


def glossary_for(text, terms):
    low = text.lower()
    hits = []
    for t in terms:
        if re.search(r"(?<![a-z])" + re.escape(t["en"].lower()) + r"(?![a-z])", low):
            line = f"- {t['en']} → {t['uk']}"
            if t.get("note"):
                line += f"  ({t['note']})"
            hits.append(line)
    return hits


def ui_terms(strings, tr):
    """Короткі написи інтерфейсу (кнопки, вкладки), вже перекладені, — як глосарій."""
    out = []
    for s in strings:
        t = tr.get(s["key"])
        en = s["en"].strip()
        if (s["file"] != "ui" or not t or t["status"] not in ("ok", "manual")
                or len(en.split()) > 4 or not re.search(r"[A-Za-z]", en)
                or re.search(r"[{}<>]", en) or en.endswith((".", "!", "?"))):
            continue
        out.append({"en": en, "uk": t["uk"].strip()})
    return out


def build_prompt(batch, prev, nxt, file_key, terms, ui=()):
    text = " ".join(x["en"] for x in batch)
    parts = [FILE_HINTS[file_key]]
    g = glossary_for(text + " " + " ".join(p["en"] for p in prev[-3:]), terms)
    if g:
        parts.append("ГЛОСАРІЙ (використовуй саме ці переклади, відмінюй за правилами):\n" + "\n".join(g))
    u = glossary_for(text, ui)
    if u:
        parts.append("НАПИСИ ІНТЕРФЕЙСУ ГРИ (якщо текст посилається на кнопку, вкладку чи розділ — "
                     "пиши назву точно як тут, у лапках «…», не відмінюючи):\n" + "\n".join(u))
    if prev:
        ctx = "\n".join(f"EN: {p['en']}\nUK: {p['uk']}" for p in prev)
        parts.append("ПОПЕРЕДНІ РЯДКИ (вже перекладені, лише для контексту, НЕ перекладай):\n" + ctx)
    if nxt:
        parts.append("НАСТУПНІ РЯДКИ (лише для контексту, НЕ перекладай):\n"
                     + "\n".join(f"EN: {x['en']}" for x in nxt))
    items = []
    for i, x in enumerate(batch, 1):
        note = x.get("comment") or ""
        extra = EXTRA_NOTES.get(x["en"].strip()) if file_key == "content" else None
        if extra:
            note = (note + " " + extra).strip()
        head = f"[{i}]" + (f" (коментар розробників: {note})" if note else "")
        items.append(f"{head}\nEN: {json.dumps(x['en'], ensure_ascii=False)}")
    parts.append(
        f"ПЕРЕКЛАДИ ці {len(batch)} рядків. Відповідь — JSON {{\"t\": [{{\"n\": номер, \"uk\": \"переклад\"}}]}} "
        f"з рівно {len(batch)} елементами, по одному на кожен номер.\n\n" + "\n\n".join(items)
    )
    return "\n\n".join(parts)


def call_ollama(args, system, user, temperature):
    body = {
        "model": args.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "format": SCHEMA,
        "keep_alive": "30m",
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "num_ctx": args.ctx,
            "num_predict": 8192,
        },
    }
    if args.no_think:
        body["think"] = False
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        data = json.loads(r.read().decode("utf-8"))
    content = data["message"]["content"]
    out = json.loads(content)["t"]
    return {int(o["n"]): o["uk"] for o in out if isinstance(o, dict) and "n" in o}


def make_batches(rows, max_chars, max_items):
    batch, size = [], 0
    for r in rows:
        if batch and (size + len(r["en"]) > max_chars or len(batch) >= max_items):
            yield batch
            batch, size = [], 0
        batch.append(r)
        size += len(r["en"])
    if batch:
        yield batch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--file", choices=["ui", "tutorial", "content", "dialogue"], action="append",
                    help="лише ці файли (можна кілька разів)")
    ap.add_argument("--limit", type=int, help="максимум рядків (для тесту)")
    ap.add_argument("--start", type=int, default=0, help="пропустити перші N рядків файлу (для тесту)")
    ap.add_argument("--out", default=str(TRANSLATIONS), help="куди писати переклади")
    ap.add_argument("--redo-errors", action="store_true", help="перекласти заново рядки з помилками")
    ap.add_argument("--redo-all", action="store_true", help="перекласти заново все (крім ручних правок)")
    ap.add_argument("--chars", type=int, default=1800, help="макс. символів англ. тексту в партії")
    ap.add_argument("--items", type=int, default=25, help="макс. рядків у партії")
    ap.add_argument("--ctx", type=int, default=16384, help="num_ctx для Ollama")
    ap.add_argument("--temp", type=float, default=0.3)
    ap.add_argument("--no-think", action="store_true", help="вимкнути режим міркувань (для Gemma 4, Qwen)")
    args = ap.parse_args()

    strings = load_json(STRINGS)
    if not strings:
        sys.exit("Спершу запусти scripts/export_strings.py")
    terms = load_json(GLOSSARY)["terms"]
    allowed_latin = {t["en"] for t in terms}
    system = STYLE.read_text(encoding="utf-8")
    tr = load_json(args.out, {})

    order = ["ui", "tutorial", "content", "dialogue"]
    files = args.file or order
    total_done = 0
    t0 = time.time()

    for fk in [f for f in order if f in files]:
        rows = sorted((x for x in strings if x["file"] == fk), key=lambda x: x["order"])
        rows = rows[args.start:]
        if args.limit:
            rows = rows[:args.limit]
        index = {r["key"]: i for i, r in enumerate(rows)}

        # заглушки та дублікати
        todo = []
        done_by_en = {r["en"]: tr[r["key"]]["uk"] for r in rows
                      if r["key"] in tr and tr[r["key"]]["status"] in ("ok", "manual")
                      and tr[r["key"]].get("src") == src_hash(r["en"])}
        for r in rows:
            cur = tr.get(r["key"])
            src = src_hash(r["en"])
            if cur and cur["status"] == "manual":
                continue  # ручну правку не чіпаємо; якщо оригінал змінився, review.py це покаже
            if cur and cur.get("src") != src:
                cur = None  # оригінал у грі змінився (або запис без відбитка)
            if cur and cur["status"] in ("ok", "skip") and not args.redo_all:
                continue
            if cur and cur["status"] == "error" and not (args.redo_errors or args.redo_all):
                continue
            if is_stub(r["en"]) or not re.search(r"[A-Za-z]", r["en"]):
                tr[r["key"]] = {"src": src, "status": "skip"}
                continue
            if r["en"] in done_by_en and not args.redo_all:
                tr[r["key"]] = {"src": src, "uk": done_by_en[r["en"]], "status": "ok", "model": "dup"}
                continue
            todo.append(r)
        save_json(args.out, tr)
        ui = ui_terms(strings, tr) if fk != "ui" else []
        if fk != "ui" and not ui:
            print("  (увага: інтерфейс ще не перекладено — назви кнопок не будуть узгоджені)")
        print(f"\n=== {fk}: треба перекласти {len(todo)} із {len(rows)}"
              + (f", написів UI в глосарії: {len(ui)}" if ui else ""))

        for batch in make_batches(todo, args.chars, args.items):
            first = index[batch[0]["key"]]
            prev = []
            for r in rows[max(0, first - 5):first]:
                t = tr.get(r["key"])
                if t and t["status"] in ("ok", "manual"):
                    prev.append({"en": r["en"], "uk": t["uk"]})
            last = index[batch[-1]["key"]]
            nxt = rows[last + 1:last + 3] if fk == "dialogue" else []

            pending = list(batch)
            for attempt in range(3):
                if not pending:
                    break
                temp = args.temp + 0.2 * attempt
                if attempt == 0:
                    groups = [pending]
                else:  # повтор — поштучно, з описом помилки
                    groups = [[p] for p in pending]
                pending = []
                for g in groups:
                    user = build_prompt(g, prev, nxt, fk, terms, ui)
                    if attempt > 0 and g[0]["key"] in tr and tr[g[0]["key"]].get("errors"):
                        user += ("\n\nМИНУЛОГО РАЗУ БУЛИ ПОМИЛКИ, виправ їх: "
                                 + "; ".join(tr[g[0]["key"]]["errors"]))
                    try:
                        res = call_ollama(args, system, user, temp)
                    except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError) as e:
                        print(f"  ! запит не вдався ({e}), повтор…")
                        res = {}
                    for i, r in enumerate(g, 1):
                        uk = res.get(i, "")
                        errs = validate(r["en"], uk, allowed_latin)
                        if not errs:
                            tr[r["key"]] = {"src": src_hash(r["en"]), "uk": uk, "status": "ok",
                                            "model": args.model}
                        else:
                            tr[r["key"]] = {"src": src_hash(r["en"]), "uk": uk, "status": "error",
                                            "errors": errs, "model": args.model}
                            pending.append(r)
            save_json(args.out, tr)
            total_done += len(batch)
            ok = sum(1 for r in batch if tr[r["key"]]["status"] == "ok")
            el = time.time() - t0
            print(f"  [{fk}] +{len(batch)} (ok {ok}/{len(batch)}) | всього {total_done} | "
                  f"{el / 60:.1f} хв, {el / max(total_done, 1):.1f} с/рядок")
            for r in batch:
                if tr[r["key"]]["status"] == "error":
                    print(f"    ✗ {r['key']}: {tr[r['key']]['errors']}")

    stats = {}
    for v in tr.values():
        stats[v["status"]] = stats.get(v["status"], 0) + 1
    print(f"\nГотово. Статуси: {stats}. Файл: {args.out}")


if __name__ == "__main__":
    main()
