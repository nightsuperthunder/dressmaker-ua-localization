# Dressmaker — Ukrainian fan localization

Project: translate the Unity game **Dressmaker** (EN → UK) with a local LLM and ship it to the community as a BepInEx mod.
User-facing language: **Ukrainian** (answer the user in Ukrainian). Code comments/docstrings are in Ukrainian — keep that style.

## Working agreement (important)
- **The user is cost-sensitive about Claude tokens.** Bulk work (translating, proofreading hundreds of strings) must go to the **local LLM via the scripts**, not be done by Claude. Claude's role: scripts, glossary, style guide, prompts, plugin code, analysing *small samples*, fixing a handful of strings.
- Long jobs: run in background (`scripts/run_all.py` keeps Windows awake itself), don't poll.
- Ask before downloading anything (fonts, tools, packages).
- **Never commit generated artifacts.** `work/backtranslate.json` (contains English back-translations of the game text!), `work/suspects.txt`, `work/context_review_state.json`, CSVs, logs — all git-ignored. Only `work/translations.json` is tracked. Check `git status` before `git add -A`.
- **Never commit original game texts** (copyrighted): no `*.yaml` table exports, no `work/strings.json`, no `en` field in `translations.json`, no English text dumps. They are git-ignored; every contributor extracts them from their own game copy.
- Commits: author only `nightsuperthunder` (already set in repo git config), **no `Co-Authored-By` or other Claude attribution** in commits, PRs, releases.

## Layout
```
content.yaml dialoge.yaml tutoriarl.yaml ui.yaml   # OPTIONAL local YAML exports of the game tables (git-ignored; only needed by import_strings.py)
glossary.json        # term → translation (+note). Injected into prompts when term appears in batch.
style_guide.md       # system prompt for the model (style, "ви" address, tech rules). Edit to steer the model.
scripts/             # pipeline (Python 3.14, PyYAML, UnityPy for inspection only)
work/strings.json        # source strings extracted from the game (key, file, id, order, en, comment) — LOCAL ONLY, git-ignored
work/translations.json   # THE translation database (source of truth) — committed, contains no English
work/review.csv, work/review_errors.csv, work/proofread_log.csv, work/run.log
out/*.yaml           # translated YAML in original format (not used by the mod; kept as alternative delivery)
mod/DressmakerUA/    # BepInEx 5 plugin (C#, netstandard2.1)
mod/README_UA.txt    # end-user install instructions (goes into zip)
mod/fonts/           # optional .ttf/.otf copied into the mod (currently empty)
mod/dist/, mod/DressmakerUA.zip   # build output / community package
```
Old files `english_strings.txt`, `tutoriarl_strings*.txt` are leftovers from earlier regex scripts — obsolete.

## Source data facts
- Unity Localization StringTables (`m_TableData[]` with `m_Id`, `m_Localized`, `m_Metadata.m_Items[].rid`). Translator comments live in `references.RefIds[].data.m_CommentText` (1101 of them) — exported as `comment`.
- 5886 strings: ui 208, tutorial 71, content 1930, dialogue 3677.
- Collections in game: `UI`, `Tutorial`, `Content`, `Dialogue` (tables named `<Collection>_<code>`). File key → collection: ui→UI, tutorial→Tutorial, content→Content, dialogue→Dialogue.
- Must be preserved verbatim: rich-text tags (`<i>`, `<b>`, `<size=60%>`, `<style=c1>`, `<color=#…>`, `<sprite=0>`, Febucci TextAnimator tags `<shake> <incr> <bounce> <pend> <rainb> <fadeloop>`), placeholders `{0}`, `{1:0.00}`, `{0:list:{}|, }` (SmartFormat), speaker prefix `QuestGiver:\t`, `\n`, and `\:` (escaped colon in Smart strings — every colon in such a string must be `\:`).
- 252 `Stub …` strings are dev placeholders → status `skip`, left in English.
- Content entries 446–464 (`Blue`, `Silk`, …) are substituted into sentences as `{0}`/`{1}`. Rule (style_guide §2): translate colours as masc. adjective, fabrics as nominative noun; build sentences like «де переважав {0} колір», «основна тканина — {1}». ~120 such dialogue lines need in-game checking.
- Player (Dressmaker) gender is undefined → glossary «Кравчиня», style guide says avoid gendered forms addressed to the player. Open decision for the user.
- `Hemstitch` = kingdom name (Гемстіч), not the stitch. `Patterns` = викрійки, not візерунки. `Discord` stays Latin. «Dressmaker» as game title (credits) stays Latin.

## Pipeline (scripts/)
| Step | Command | Notes |
|---|---|---|
| Export | `python scripts/export_strings.py [--game <dir>] [--yaml]` | Reads `Dressmaker_Data/StreamingAssets/aa/StandaloneWindows64/localization-string-tables-english(en)_assets_all.bundle` with UnityPy (`pip install UnityPy`) → work/strings.json. Same dict structure as the YAML (`m_TableData`, `references.RefIds`), tables `UI_en`, `Tutorial_en`, `Content_en`, `Dialogue_en`. `--yaml` reads local YAML exports instead. Note: PyYAML parses bare `Yes`/`No` as booleans — the bundle is the more exact source. |
| Translate | `python scripts/translate.py [--file X] [--limit N] [--out path] [--redo-errors] [--redo-all] [--model M] [--no-think]` | Ollama `/api/chat`, JSON-schema output, batches (≤1800 chars / 25 items), 5 previous translated lines + 2 next as context, glossary filtered per batch, **UI auto-glossary** (short translated UI labels fed to later files), per-item validation, failed items retried individually (3 attempts, error text fed back). Resumable. Duplicate EN strings reuse translation (`model: "dup"`). |
| Proofread | `python scripts/proofread.py [--file X] [--limit N] [--revert]` | Same model as editor. Only `ok` rows, once (`proofed: true`). Keeps `uk_before_proof`; logs to work/proofread_log.csv. Rejected if new text fails validation. |
| Review | `python scripts/review.py export [--errors] [--tr] [--csv]` / `import` / `stats` | CSV (utf-8-sig) for Excel. Import marks changed rows `manual`. Rows with placeholders get a "ПЕРЕВІР" warning. |
| Import YAML | `python scripts/import_strings.py [--allow-missing] [--locale uk]` | Optional/legacy (mod doesn't need it); requires local YAML exports. Line-based replacement of `m_Localized` (JSON-quoted), preserves LF/CRLF, re-parses to verify. |
| Full run | `python scripts/run_all.py` | translate → redo-errors → proofread → stats → review exports → import. Uses SetThreadExecutionState to prevent sleep. ~2 h on RTX 5070 Ti. |
| Find meaning errors | `python scripts/find_issues.py [--file X]` | 3 stages: `backtranslate.py` (MamayLM re-translates UK→EN literally, embeddinggemma:300m cosine vs original) → `backtranslate.py --judge` (gemma4:26b-a4b compares ORIGINAL vs BACK, English-only task) → `context_review.py --only-keys work/suspects.txt` (same big model sees EN+UK+neighbouring lines, proposes fixes). Output: work/context_review.csv in review.py format → skim, delete rows, `review.py import --csv`. Measured funnel on 500 dialogue lines: 134 flagged → 31 final, mostly genuine (Regency "gay"=весела, lost "kid" pun, "beside herself", ти/ви slips). **Blind spots:** grammar/gender agreement and pronoun gender are invisible to back-translation (English erases them); cosine similarity alone did NOT rank known errors highly — the judge stage is what works. MamayLM as an open-ended reviewer is too weak (1/6 known errors, 111 false positives per 500). |
| Mod | `python scripts/build_mod.py [--install] [--with-bepinex <dir>] [--game <dir>]` | dotnet build + export `translations/uk.json` + zip. |

`scripts/common.py`: paths, Unity YAML loader (multi-constructor for `tag:unity3d.com,2011:`), `validate(en, uk, allowed_latin)`:
tags multiset equal, placeholders multiset equal, prefix kept, `\n` count, `\:` rule, Cyrillic present, ≥3 leftover English words, length sanity, placeholder-only / roman-numeral strings must stay identical, no spurious outer «…».

### translations.json record
`key` = `"<file>:<m_Id>"` → `{src, uk?, status, model?, errors?, proofed?, uk_before_proof?}`.
`src` = `common.src_hash(en)` (first 12 hex of SHA-1 of the English source) — lets scripts detect changed originals without storing game text. English text always comes from `work/strings.json`.
Statuses: `ok` (model, validated) · `manual` (human/Claude edit — never overwritten by scripts) · `skip` (stub/no letters, left as in the game) · `error` (failed validation; not exported to mod/YAML).
If `src` doesn't match the current source, translate.py treats the record as untranslated (manual ones are kept), review.py flags it, build_mod.py warns. `skip` records have no `uk` (the game text is used as-is).

### Model
Ollama, default `hf.co/INSAIT-Institute/MamayLM-Gemma-3-12B-IT-v2.0-GGUF:Q8_0` (Ukrainian fine-tune of Gemma 3 12B), ~1.1–2.5 s/string. Options: temp 0.3 (proofread 0.2), num_ctx 16384, keep_alive 30m. Alternatives installed: `gemma3:12b`, `gemma4:12b`; `gemma4:26b-a4b-it-q4_K_M` suggested (use `--no-think`).
Known model weaknesses: calques, gender slips, ignores placeholder-sentence rule, drops `<i>` tags occasionally, **wraps whole strings in «»** (was 3185 strings — fixed by script; prompt + validator now guard it).

## Current state (2026-09-22)
- All strings translated + proofread (1188 changed). Stats: ok 5492, manual 59, skip 335, error 0. 1 validator false positive (credits line with Latin names).
- UI hand-corrected (45 rows, `manual`); 14 dialogue rows hand-fixed (lost `<i>` tags, quotes).
- Mod built and installed into the game; main menu verified in Ukrainian with screenshot.
- TODO / open: in-game playtest (dialogues, tutorial, dress editor, newspaper, `{0}` sentences, language menu switching); better Cyrillic fonts (EB Garamond has official Cyrillic under OFL; find matches for Amaranth/Cantora One/Freude) — needs download permission; player gender decision; localized images (5 in `Images` asset table: shop name, newspaper title) stay English.

## Game internals (from decompiling with ilspycmd)
Game: `E:\Games\SteamLibrary\steamapps\common\Dressmaker` — Unity **6000.3.4**, **Mono** (`Dressmaker_Data/Managed`), Unity Localization + Addressables.
- Bundles: `Dressmaker_Data/StreamingAssets/aa/StandaloneWindows64/localization-string-tables-<lang>(<code>)_assets_all.bundle` (e.g. `english(en)`); locales en, ja, zh-Hans, af (af is hidden and partially translated). This is where export_strings.py gets the English source.
- `LanguageSelectorPopup.Populate()` lists `LocalizationSettings.AvailableLocales.Locales` except `af`; label = private static `NativeName(locale)` (CultureInfo.NativeName).
- `PlayerOptionsLocaleSelector.GetStartupLocale` (IStartupLocaleSelector) restores `PlayerOptions.Current.preferredLanguage`; otherwise Unity's system-language selector picks the locale (the user's Windows is Ukrainian → game starts in `uk`).
- Fonts: `LocaleFontFallbacks` (Resources asset) maps latin TMP font → per-locale font; `LocaleFontApplier.Apply` sets `latin.fallbackFontAssetTable`; `LocalizedTextFont` swaps the whole font. All go through `LocaleFontFallbacks.Get(latin, locale)`.
- Game TMP fonts: Amaranth (Regular/Bold/Italic), CantoraOne, EBGaramond (Medium/MediumItalic), Freude — static atlases, no Cyrillic. Source fonts present: LiberationSans, SourceHan*, KaiseiTokumin, MPLUSRounded1c, PerfectDOSVGA437.
- Decompiled sources were in the session scratchpad (temporary). Regenerate: `ilspycmd -p -o <dir> -r <Managed> <Managed>/Assembly-CSharp.dll` (ilspycmd installed as global dotnet tool, `~/.dotnet/tools`).

## Mod (mod/DressmakerUA/Plugin.cs)
BepInEx **5.4.23.5** x64 (installed in game folder; zip also in session scratchpad — re-download from GitHub releases if needed). Plugin GUID `ua.dressmaker.localization`.
- `Awake`: load `translations/<code>.json` (`{Collection: {id: text}}`), set `LocalizationSettings.StringDatabase.TableProvider = UkTableProvider`, Harmony-patch, add locale after init.
- `EnsureLocale`: `Locale.CreateLocale("uk")`, name from config, `FallbackLocale(en)` metadata, `AssetDatabase.UseFallback = true`, `AddLocale`. Also called from a Harmony prefix on `PlayerOptionsLocaleSelector.GetStartupLocale` (so a saved "uk" preference resolves at startup).
- `UkTableProvider.ProvideTableAsync`: for our locale + StringTable → load `<Collection>_en` via Addressables, chain → build new StringTable (SharedData from en, every en entry, text from json or en fallback, copies `IsSmart`). Asset tables → return `default` (game falls back to en via FallbackLocale; returning the en asset table caused a blank logo).
- Text that doesn't fit the game's fixed-width buttons (Ukrainian words are longer): `ApplyAutoSize` turns on TMP auto-sizing for our locale only — authored `fontSize` becomes `fontSizeMax`, min = `AutoSizeMinRatio` (config, default 0.6). Applied on `sceneLoaded` (`Resources.FindObjectsOfTypeAll<TMP_Text>`) and via a Harmony postfix on `TextMeshProUGUI.OnEnable` for runtime-created labels. Verified in game. Fallback for bad cases: shorten the label in translations (`manual`).
- `LocalizedContent.Get(table, key, fallback)` postfix: the game looks pattern-panel names up as `Panel/<PrettyNameNoSpaces>` (see `PatternPanelDefinition.NameKey`), but numbered variants (`Panel/BodiceButtonPlacket1`) have no key in the shared table, so the game falls back to the English `prettyName` (true for ja/zh too). When the result equals the fallback and the key ends in digits, the plugin looks up the base key and appends the number.
- Harmony postfixes: `LocaleFontFallbacks.Get` → Cyrillic fallback `TMP_FontAsset` for our locale (file `fonts/<latin font name>.ttf`, else `fonts/default.ttf`, else OS font from config `OsFontFallback`, default "Georgia"); `LanguageSelectorPopup.NativeName` → "Українська".
- Config file in game: `BepInEx/config/ua.dressmaker.localization.cfg` (LocaleCode, DisplayName, OsFontFallback). Log: `BepInEx/LogOutput.log` (look for `Dressmaker Ukrainian` lines: strings loaded, locale added, per-table translated counts).
- Build requires .NET SDK (10.x present); references game DLLs + BepInEx core via `GameDir` property in csproj. Close the game before `--install` (DLL lock).
- Testing done so far: launch exe, wait for log, screenshot via PowerShell `CopyFromScreen` into scratchpad, view with Read.
