"""Детермінований переклад назв деталей викрійок (Content: «Skirt Tier 2 Left Back» тощо).

Модель перекладала кожну назву окремо, тому стиль скакав («ліворуч/зліва/лівий», «спинка/ззаду»,
«опустити» замість «нижній»). Тут назва розбирається на основу (деталь), номер ярусу/волана
і позицію, і складається за одним шаблоном:  «<Деталь>[, ярус N]: <ліва задня> частина».

  python scripts/panel_names.py            # показати зміни
  python scripts/panel_names.py --apply    # записати як manual
"""
import argparse
import json
import sys

from common import TRANSLATIONS, WORK, load_json, save_json, src_hash, validate

# Діапазони order у content, де лежать назви деталей
RANGES = [(872, 1251), (1265, 1283), (1431, 1575)]

NORM = {'RIght': 'Right', 'front': 'Front', 'back': 'Back', 'Sleev': 'Sleeve',
        'F': 'Front', 'B': 'Back', 'L': 'Left', 'R': 'Right'}
POS = {'Left', 'Right', 'Front', 'Back', 'Upper', 'Lower', 'Inner', 'Outer',
       'Top', 'Bottom', 'Middle', 'Central'}

# основа → (шаблон, (ліва, права) форми для {s} або None, прапорці)
# {s} — сторона вбудовується в назву; без {s} сторона йде в «: ліва … частина».
# 'vm' — Upper/Lower стають «верхній/нижній» перед іменником (чол. рід); 'noup' — Upper ігнорується.
LR_M = ('Лівий', 'Правий')
LR_F = ('Ліва', 'Права')
LR_N = ('Ліве', 'Праве')
LR_GEN = ('лівого', 'правого')
LR_GEN_F = ('лівої', 'правої')
BASE = {
    '': ('', None, ''),
    'Apron Belt': ('Пасок фартуха', None, ''),
    'Belt': ('Пасок', None, ''),
    'Bodice': ('Ліф', None, ''),
    'Bodice Belt': ('Пасок ліфа', None, ''),
    'Bodice Button Placket': ('Планка ліфа з ґудзиками', None, ''),
    'Bodice Chest': ('Нагрудна частина ліфа', None, ''),
    'Bodice Collar': ('Комір ліфа', None, ''),
    'Bodice Cowl': ('Хомут ліфа', None, ''),
    'Bodice Cuff': ('Манжета ліфа', None, ''),
    'Bodice Cup': ('{s} чашка ліфа', LR_F, ''),
    'Bodice Eyelet Placket': ('{s} планка ліфа з люверсами', LR_F, ''),
    'Bodice Frill': ('Рюш ліфа', None, ''),
    'Bodice Lace': ('Мереживо ліфа', None, ''),
    'Bodice Neck': ('Горловина ліфа', None, ''),
    'Bodice Neck Band': ('Обшивка горловини ліфа', None, ''),
    'Bodice Neck Bow': ('Бант на горловині ліфа', None, ''),
    'Bodice Neck Strap': ('Бретель ліфа навколо шиї', None, ''),
    'Bodice Ribbon': ('Стрічка ліфа', None, ''),
    'Bodice Ruffle': ('Волан ліфа', None, ''),
    'Bodice Shoulder': ('{s} плече ліфа', LR_N, ''),
    'Bodice Sleeve Attachment': ('Пришивна частина {s} рукава', LR_GEN, ''),
    'Bodice Stays': ('Корсет ліфа', None, ''),
    'Bodice Strap': ('{s} бретель ліфа', LR_F, ''),
    'Bodice Strap Ribbon': ('Стрічка {s} бретелі ліфа', LR_GEN_F, ''),
    'Bodice Trim': ('Оздоблення ліфа', None, ''),
    'Bodice Undershirt': ('Нижня сорочка', None, ''),
    'Bodice Undershirt Placket': ('Планка нижньої сорочки', None, ''),
    'Bodice Undertop': ('Нижній топ', None, ''),
    'Bodice Undertop Placket': ('Планка нижнього топа', None, ''),
    'Bodice Waist': ('Талія ліфа', None, ''),
    'Bodice Waistband': ('Пояс ліфа', None, ''),
    'Bodice Yoke': ('Кокетка ліфа', None, ''),
    'Bolero': ('Болеро', None, ''),
    'Bolero Ribbon': ('Стрічка болеро', None, ''),
    'Bow': ('Бант', None, ''),
    'Bow Ears': ('Петлі банта', None, ''),
    'Bow Tail': ('Кінець банта', None, ''),
    'Bow Tail A': ('Кінець банта A', None, ''),
    'Collar': ('Комір', None, ''),
    'Collar Bow': ('Бант коміра', None, ''),
    'Collar Frill': ('Рюш коміра', None, ''),
    'Collar Panel': ('Вставка коміра', None, ''),
    'Collar Placket': ('Планка коміра', None, ''),
    'Collar Ribbon': ('Стрічка коміра', None, ''),
    'Collar Ruffle': ('Волан коміра', None, 'vm'),
    'Collar Shoulder Pad': ('Накладка коміра на {s} плече', ('ліве', 'праве'), ''),
    'Dirndl': ('Дірндль', None, ''),
    'Dirndl Strap': ('{s} бретель дірндля', LR_F, ''),
    'Jacket': ('Жакет', None, ''),
    'Jacket Collar': ('Комір жакета', None, ''),
    'Jacket Collar Trim': ('Оздоблення коміра жакета', None, ''),
    'Jacket Placket': ('Планка жакета', None, ''),
    'Jacket Sleeve': ('{s} рукав жакета', LR_M, ''),
    'Jacket Trim': ('Оздоблення жакета', None, ''),
    'Jacket Yoke': ('Кокетка жакета', None, ''),
    'Overskirt': ('Верхня спідниця', None, ''),
    'Peplum': ('Баска', None, ''),
    'Ruffle': ('Волан', None, ''),
    'Shoulder': ('{s} плече', LR_N, ''),
    'Skirt': ('Спідниця', None, ''),
    'Skirt Apron': ('Фартух спідниці', None, ''),
    'Skirt Apron Ruffle': ('Волан фартуха спідниці', None, ''),
    'Skirt Belt': ('Пасок спідниці', None, ''),
    'Skirt Bow': ('Бант спідниці', None, ''),
    'Skirt Drop Waist': ('Спідниця із заниженою талією', None, ''),
    'Skirt Frill': ('Рюш спідниці', None, 'vm'),
    'Skirt Hip': ('Кокетка спідниці', None, ''),
    'Skirt Insert': ('Вставка спідниці', None, ''),
    'Skirt Panel': ('Полотнище спідниці', None, ''),
    'Skirt Peplum': ('Баска спідниці', None, ''),
    'Skirt Placket': ('Планка спідниці', None, ''),
    'Skirt Ribbon': ('Стрічка спідниці', None, ''),
    'Skirt Ruffle': ('Волан спідниці', None, ''),
    'Skirt Tier': ('Ярус спідниці', None, ''),
    'Skirt Train': ('Шлейф спідниці', None, ''),
    'Skirt Trim': ('Оздоблення спідниці', None, ''),
    'Skirt Waist': ('Талія спідниці', None, ''),
    'Skirt Waist Band': ('Пояс спідниці', None, ''),
    'Sleeve': ('{s} рукав', LR_M, 'vm'),
    'Sleeve Band': ('Обшивка {s} рукава', LR_GEN, ''),
    'Sleeve Bishop': ('{s} рукав-єпископ', LR_M, 'vm'),
    'Sleeve Cap': ('Окат {s} рукава', LR_GEN, ''),
    'Sleeve Cuff': ('Манжета {s} рукава', LR_GEN, ''),
    'Sleeve Cuff Frill': ('Рюш манжети {s} рукава', LR_GEN, ''),
    'Sleeve Flounce': ('Волан {s} рукава', LR_GEN, ''),
    'Sleeve Puff': ('Буф {s} рукава', LR_GEN, 'noup'),
    'Sleeve Shoulder': ('Плечова частина {s} рукава', LR_GEN, ''),
    'Sleeve Wing': ('Крильце {s} рукава', LR_GEN, ''),
    'Stays': ('Корсет', None, ''),
    'Stays Eyelet Placket': ('{s} планка корсета з люверсами', LR_F, ''),
    'Stays Ribbon': ('Стрічка корсета', None, ''),
    'Stays Strap': ('{s} бретель корсета', LR_F, ''),
    'Undershirt': ('Нижня сорочка', None, ''),
    'Undershirt Frill': ('Рюш нижньої сорочки', None, ''),
    'Underskirt': ('Нижня спідниця', None, ''),
    'Undertop': ('Нижній топ', None, ''),
    'Undertop Placket': ('Планка нижнього топа', None, ''),
    'Waist': ('Талія', None, ''),
    'Waist Band': ('Пояс', None, ''),
}
# Назви, які не вкладаються в шаблон (EN → UK)
OVERRIDE = {
    'Collar Front and Back': 'Комір: передня й задня частини',
    'Bodice Cup Bottom Top Left': 'Ліва чашка ліфа: верх нижньої частини',
    'Bodice Cup Bottom Top Right': 'Права чашка ліфа: верх нижньої частини',
    'Bodice Front Chest': 'Нагрудна частина ліфа',
    'Bow Tail B': 'Кінець банта B',
}

VERT = {'Upper': 'верхня', 'Top': 'верхня', 'Lower': 'нижня', 'Bottom': 'нижня',
        'Middle': 'середня', 'Central': 'центральна'}
VERT_M = {'Upper': 'верхній', 'Lower': 'нижній'}
SIDE = {'Left': 'ліва', 'Right': 'права'}
DEPTH = {'Front': 'передня', 'Back': 'задня'}
IO = {'Inner': 'внутрішня', 'Outer': 'зовнішня'}


def compose(en):
    if en.strip() in OVERRIDE:
        return OVERRIDE[en.strip()]
    toks = [NORM.get(t, t) for t in en.split()]
    base, nums, pos = [], [], []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in ('Tier', 'Ruffle') and i + 1 < len(toks) and toks[i + 1].isdigit():
            nums.append(('ярус' if t == 'Tier' else 'волан') + ' ' + str(int(toks[i + 1])))
            i += 2
            continue
        if t.isdigit():  # «Left Sleeve Tier 3» уже з'їдено вище; голі цифри — номер
            nums.append(str(int(t)))
        elif t in POS:
            if t not in pos:
                pos.append(t)
        else:
            base.append(t)
        i += 1
    key = ' '.join(base)
    if key not in BASE:
        raise KeyError(f'невідома основа «{key}» у «{en}»')
    tmpl, lr, flags = BASE[key]
    side = next((p for p in pos if p in SIDE), None)
    if lr:
        if side:
            pos.remove(side)
        s = lr[side == 'Right'] if side else ''
        if 'vm' in flags:
            v = next((p for p in pos if p in VERT_M), None)
            if v:
                pos.remove(v)
                s = (s + ' ' + VERT_M[v]).strip()
        text = tmpl.replace('{s}', s).replace('  ', ' ').strip()
        text = text[:1].upper() + text[1:]
    else:
        text = tmpl
        if 'vm' in flags:
            v = next((p for p in pos if p in VERT_M), None)
            if v:
                pos.remove(v)
                text = VERT_M[v].capitalize() + ' ' + text[:1].lower() + text[1:]
    if 'noup' in flags and 'Upper' in pos:
        pos.remove('Upper')
    if nums:
        text = (text + ', ' if text else '') + ', '.join(nums)
        text = text[:1].upper() + text[1:]
    if pos:
        adj = [VERT[p] for p in pos if p in VERT] + [SIDE[p] for p in pos if p in SIDE] \
            + [DEPTH[p] for p in pos if p in DEPTH] + [IO[p] for p in pos if p in IO]
        part = ' '.join(adj) + ' частина'
        text = f'{text}: {part}' if text else part[:1].upper() + part[1:]
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    strings = json.load(open(WORK / 'strings.json', encoding='utf-8'))
    T = load_json(TRANSLATIONS)
    changed = 0
    for s in sorted(strings, key=lambda s: s['order']):
        if s['file'] != 'content' or not any(a <= s['order'] <= b for a, b in RANGES):
            continue
        uk = compose(s['en'])
        err = validate(s['en'], uk, set())
        old = T.get(s['key'], {}).get('uk')
        if uk == old:
            continue
        changed += 1
        print(f"{s['en']}  =>  {uk}" + (f'   !! {err}' if err else ''))
        if args.apply and not err:
            T[s['key']] = {'src': src_hash(s['en']), 'uk': uk, 'status': 'manual'}
    print(f'змінено: {changed}', file=sys.stderr)
    if args.apply:
        save_json(TRANSLATIONS, T)


if __name__ == '__main__':
    main()
