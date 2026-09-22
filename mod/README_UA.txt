Dressmaker — українська локалізація (фанатська)
==============================================

ВСТАНОВЛЕННЯ
1. Steam → Dressmaker → ПКМ → Керування → Переглянути локальні файли.
2. Розпакуйте ВЕСЬ вміст архіву в цю папку (поруч з Dressmaker.exe).
   Має вийти: Dressmaker.exe, winhttp.dll, doorstop_config.ini, папка BepInEx.
3. Запустіть гру. Якщо мова Windows українська — гра одразу буде українською.
   Інакше: Налаштування → Мова → «Українська».

Файли гри не змінюються, тож оновлення гри переклад не ламають.

ВИДАЛЕННЯ
Видаліть winhttp.dll, doorstop_config.ini і папку BepInEx з папки гри.

ДЛЯ ПЕРЕКЛАДАЧІВ
- Переклад: BepInEx/plugins/DressmakerUA/translations/uk.json
  (таблиця → ID рядка → текст; відсутні рядки показуються англійською).
- Шрифти: покладіть .ttf/.otf з кирилицею в BepInEx/plugins/DressmakerUA/fonts/
    default.ttf                    — для всього тексту;
    <назва шрифту гри>.ttf         — для конкретного шрифту, напр. "EBGaramond-Medium SDF.ttf".
  Без шрифтів використовується системний Georgia (змінюється в BepInEx/config/ua.dressmaker.localization.cfg).
- Журнал: BepInEx/LogOutput.log

Використовується BepInEx 5 (https://github.com/BepInEx/BepInEx, LGPL-2.1).
