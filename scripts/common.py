"""Спільні функції: читання Unity YAML, перевірка тегів/плейсхолдерів, шляхи."""
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
OUT = ROOT / "out"
STRINGS = WORK / "strings.json"
TRANSLATIONS = WORK / "translations.json"
GLOSSARY = ROOT / "glossary.json"
STYLE = ROOT / "style_guide.md"

DEFAULT_GAME = r"E:\Games\SteamLibrary\steamapps\common\Dressmaker"
BUNDLE_DIR = r"Dressmaker_Data\StreamingAssets\aa\StandaloneWindows64"
EN_BUNDLE = "localization-string-tables-english(en)_assets_all.bundle"

# Короткий ключ -> назва колекції в грі (таблиці <Колекція>_<мова>)
COLLECTIONS = {"ui": "UI", "tutorial": "Tutorial", "content": "Content", "dialogue": "Dialogue"}

# Файл гри (YAML-експорт, необов'язковий) -> короткий ключ
FILES = {
    "ui": "ui.yaml",
    "tutorial": "tutoriarl.yaml",
    "content": "content.yaml",
    "dialogue": "dialoge.yaml",
}


class UnityLoader(yaml.SafeLoader):
    pass


def _unity_tag(loader, suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


UnityLoader.add_multi_constructor("tag:unity3d.com,2011:", _unity_tag)


def load_unity_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=UnityLoader)["MonoBehaviour"]


def src_hash(en):
    """Відбиток англійського оригіналу: у репозиторії зберігаємо його замість самого тексту гри."""
    return hashlib.sha1(en.encode("utf-8")).hexdigest()[:12]


def load_json(path, default=None):
    if not Path(path).exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    tmp.replace(path)


# ---------- перевірка перекладу ----------

TAG_RE = re.compile(r"<[^<>]+>")
PH_RE = re.compile(r"\{[^{}]*\}")
PREFIX_RE = re.compile(r"^[A-Za-z]+:\t")  # "QuestGiver:\t"
CYR_RE = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
LAT_WORD_RE = re.compile(r"\b[A-Za-z]{4,}\b")


def _multiset(items):
    return sorted(items)


def validate(en, uk, allowed_latin=()):
    """Повертає список проблем (порожній = все добре)."""
    errs = []
    if not uk or not uk.strip():
        return ["порожній переклад"]
    core = TAG_RE.sub("", en)
    while PH_RE.search(core):
        core = PH_RE.sub("", core)
    core = core.strip()
    if ((not re.search(r"[A-Za-z]{2,}", core) and re.search(r"[А-Яа-яІіЇїЄєҐґ]{3,}", uk))
            or (re.fullmatch(r"[IVXLC]+", core) and uk != en)):
        # рядок лише з плейсхолдерів/розділових знаків або римська цифра — має лишитися як є
        errs.append("цей рядок не треба перекладати — залиш точно як в оригіналі")
    if _multiset(TAG_RE.findall(en)) != _multiset(TAG_RE.findall(uk)):
        errs.append(f"теги не збігаються: {TAG_RE.findall(en)} -> {TAG_RE.findall(uk)}")
    if _multiset(PH_RE.findall(en)) != _multiset(PH_RE.findall(uk)):
        errs.append(f"плейсхолдери не збігаються: {PH_RE.findall(en)} -> {PH_RE.findall(uk)}")
    m = PREFIX_RE.match(en)
    if m and not uk.startswith(m.group(0)):
        errs.append(f"рядок має починатися з {m.group(0)!r}")
    if en.count("\n") != uk.count("\n"):
        errs.append("кількість переносів рядка \\n не збігається")
    if "\\:" in en:
        # smart string: кожна двокрапка поза {} має бути екранована
        stripped = PH_RE.sub("", uk)
        if re.search(r"(?<!\\):", PREFIX_RE.sub("", stripped)):
            errs.append("у цьому рядку двокрапку треба писати як \\:")
    if re.search(r"[A-Za-z]", en) and not CYR_RE.search(uk):
        # дозволяємо, якщо рядок — це лише імена з глосарію / теги
        if re.search(r"[A-Za-z]{2,}", core) and len(core) > 3 and core not in allowed_latin:
            errs.append("немає кирилиці — схоже, не перекладено")
    leftover = [w for w in LAT_WORD_RE.findall(TAG_RE.sub("", PREFIX_RE.sub("", uk)))
                if w not in allowed_latin]
    if len(leftover) >= 3:
        errs.append(f"залишилися англійські слова: {leftover[:6]}")
    en_body = PREFIX_RE.sub("", en).lstrip()
    uk_body = PREFIX_RE.sub("", uk)
    if (uk_body.startswith("«") and uk_body.endswith("»")
            and not en_body.startswith(('"', "“", "‘", "'", "«"))):
        errs.append("зайві лапки «…» навколо всього рядка — в оригіналі їх немає")
    if len(uk) > 3 * len(en) + 40:
        errs.append("переклад підозріло довгий")
    return errs
