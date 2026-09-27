"""Пошук рядків із чоловічим родом для ручної перевірки (без моделі, лише регулярні вирази).

Кравчиня і більшість персонажів — жінки, тож кожна чоловіча форма підозріла, але є й чоловіки
(герцог, містер Дервішем, привид …) — тому нічого не виправляється автоматично.

Шукає:
- дієслова минулого часу чоловічого роду («забув», «пішов», «зміг», «повернувся»);
- прикметники / дієприкметники чоловічого роду поруч з «я / ти / ви» («я радий», «ти певен»);
- звертання чоловічого роду («друже», «мій любий», «хлопче»).

  python scripts/find_masculine.py                  -> work/masculine_review.csv
  python scripts/find_masculine.py --file dialogue
Колонка errors: [Я/ТИ] — поруч займенник 1–2 особи (перевіряти першими), [3 ОСОБА] — решта.
Колонка context — попередні репліки (EN + UK), щоб зрозуміти, хто говорить.
Виправте колонку uk, зайві рядки видаліть і застосуйте:
  python scripts/review.py import --csv work/masculine_review.csv
"""
import argparse
import csv
import re

from common import STRINGS, TRANSLATIONS, WORK, load_json

WORD = r"[а-щьюяєіїґ’'-]"
# минулий час ч.р.: основа + голосний + «в» (+ся/сь)
PAST_V = re.compile(rf"(?<![\w’'-])({WORD}+[аяиіуїое]в(?:ся|сь)?)(?![\w’'])", re.I)
# минулий час ч.р. без «в»: міг, ніс, помер, втік …
PAST_IRR = re.compile(rf"(?<![\w’'-])({WORD}*(?:міг|ніс|ліг|помер|вмер|втік|утік|біг|віз|ріс|звик|зник"
                      rf"|мерз|ліз|стриг|беріг|стеріг|пік|трясся|нісся))(?![\w’'])", re.I)
# дієслова на -ів (решта -ів — родовий відмінок множини: «років», «друзів»)
IV_VERBS = ("хотів", "вмів", "умів", "зумів", "радів", "вів", "сидів", "летів", "терпів", "горів", "болів",
            "велів", "стовпів", "шумів", "кипів", "зрів", "шалів", "німів", "червонів", "старів", "дурів",
            "висів", "свистів", "шипів", "блищів", "тремтів", "кричав", "мовчав", "лежав", "бачив")
NOT_VERBS = {"любов", "немов", "умов", "розмов", "норов", "справ", "вистав", "глав", "збав", "рукав",
             "вплив", "зрив", "мотив", "подив", "вияв", "вислів", "кров", "лев", "пів", "архів", "злив",
             "острів", "київ", "львів", "причал", "вив", "заголов", "відхилив", "покров", "мотузків",
             "дів", "сліз", "гнів", "співів", "перерв", "церков", "свекров", "брів", "рів", "хлів"}
PRON = re.compile(r"(?<![а-щьюяєіїґ’'])(я|ти|ви)(?![а-щьюяєіїґ’'])", re.I)
ADJ_AFTER_PRON = re.compile(
    r"(?<![а-щьюяєіїґ’'])(?:я|ти|ви)\s+(?:(?:[а-щьюяєіїґ’'-]+)\s+){0,2}?"
    r"((?:[а-щьюяєіїґ’'-]+(?:ий|ен))|радий|сам|один)(?![а-щьюяєіїґ’'])", re.I)
ADJ_STOP = {"мій", "свій", "який", "такий", "кожен", "повинен"}  # «повинен» — окремо нижче
SHORT = re.compile(r"(?<![а-щьюяєіїґ’'])(радий|певен|винен|згоден|повинен|здатен|ладен|потрібен|вартий"
                   r"|змушений|вдячний|впевнений|щасливий|зайнятий|здивований|задоволений|готовий)"
                   r"(?![а-щьюяєіїґ’'])", re.I)
VOC = re.compile(r"(?<![а-щьюяєіїґ’'])(друже|мій любий|мій дорогий|любий друже|дорогий друже|хлопче|юначе"
                 r"|синку|козаче|пане-брате)(?![а-щьюяєіїґ’'])", re.I)
CLAUSE = re.compile(r"[.!?;…—\n]+")
COLS = ["key", "file", "status", "en", "uk", "context", "comment", "errors"]


def is_past(w):
    lw = w.lower().replace("'", "’")
    base = lw[:-2] if lw.endswith(("ся", "сь")) else lw
    if base in NOT_VERBS or lw in NOT_VERBS:
        return False
    if base.endswith("їв"):
        return base == "їв"  # «покоїв», «країв» — іменники
    if base.endswith("ів"):
        return base.endswith(IV_VERBS)
    if base.endswith("ов"):
        return base.endswith("шов")  # пішов, прийшов, знайшов
    return len(base) > 3 or bool(PAST_IRR.fullmatch(lw))


def hits(uk):
    found = []
    for cl in CLAUSE.split(uk):
        words = [w for w in PAST_V.findall(cl) + PAST_IRR.findall(cl) if is_past(w)]
        words += [m.group(1) for m in ADJ_AFTER_PRON.finditer(cl) if m.group(1).lower() not in ADJ_STOP]
        words += SHORT.findall(cl)
        words += VOC.findall(cl)
        if words:
            # займенник 1–2 особи в тому ж реченні — або підмета немає зовсім («Мало не забув!»)
            first = PRON.search(cl) or not re.search(
                r"(?<![а-щьюяєіїґ’'])(він|вона|воно|вони|хтось|ніхто|[А-ЯЄІЇҐ][а-щьюяєіїґ’']+)", cl[1:])
            found.append(("Я/ТИ" if first else "3 ОСОБА", sorted(set(w.lower() for w in words))))
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", choices=["ui", "tutorial", "content", "dialogue"], action="append")
    ap.add_argument("--csv", default=str(WORK / "masculine_review.csv"))
    ap.add_argument("--ctx", type=int, default=3, help="скільки попередніх реплік показати")
    args = ap.parse_args()
    files = args.file or ["tutorial", "dialogue"]

    strings = load_json(STRINGS)
    tr = load_json(TRANSLATIONS)
    out = []
    for fk in files:
        rows = sorted((s for s in strings if s["file"] == fk), key=lambda s: s["order"])
        for i, s in enumerate(rows):
            t = tr.get(s["key"])
            if not t or not t.get("uk") or t["status"] not in ("ok", "manual"):
                continue
            h = hits(t["uk"])
            if not h:
                continue
            prio = "Я/ТИ" if any(p == "Я/ТИ" for p, _ in h) else "3 ОСОБА"
            words = sorted({w for _, ws in h for w in ws})
            ctx = "\n".join(f"EN: {p['en']}\nUK: {(tr.get(p['key']) or {}).get('uk', p['en'])}"
                            for p in rows[max(0, i - args.ctx):i])
            out.append({"key": s["key"], "file": fk, "status": t["status"], "en": s["en"], "uk": t["uk"],
                        "context": ctx, "comment": s["comment"],
                        "errors": f"[{prio}] " + ", ".join(words)})
    out.sort(key=lambda r: not r["errors"].startswith("[Я/ТИ]"))  # стабільне: порядок гри зберігається
    with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(out)
    n1 = sum(r["errors"].startswith("[Я/ТИ]") for r in out)
    print(f"{len(out)} рядків ({n1} з «я/ти/ви» або без підмета) -> {args.csv}")


if __name__ == "__main__":
    main()
