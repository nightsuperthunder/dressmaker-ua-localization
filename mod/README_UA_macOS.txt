Dressmaker — українська локалізація (фанатська), версія для macOS
================================================================

ВСТАНОВЛЕННЯ
1. Steam → ПКМ на Dressmaker → Керування → Переглянути локальні файли.
   Відкриється папка, у якій лежить Dressmaker.app.
2. Розпакуйте ВЕСЬ вміст архіву в цю папку (поруч із Dressmaker.app).
   Має вийти: Dressmaker.app, BepInEx, libdoorstop.dylib, run_bepinex.sh, install_ua_macos.sh.
3. Відкрийте Термінал (Cmd+Пробіл → «Термінал»), наберіть  sh  і пробіл,
   перетягніть у вікно Термінала файл install_ua_macos.sh і натисніть Enter.
   Скрипт напише «Готово!» і скопіює потрібний рядок у буфер обміну.
4. Steam → ПКМ на Dressmaker → Властивості → Загальні → Параметри запуску → вставте (Cmd+V).
5. Запустіть гру зі Steam. Налаштування → Мова → «Українська».

Файли гри не змінюються, тож оновлення гри переклад не ламають.

ЯКЩО НЕ ПРАЦЮЄ
- Перевірте, чи з'явився файл BepInEx/LogOutput.log після запуску гри.
  Якщо його немає — BepInEx не запустився: перевірте рядок у Параметрах запуску.
- Не вмикайте «Відкривати за допомогою Rosetta» вручну: скрипт запуску сам запускає гру
  через Rosetta (BepInEx поки не працює на чипах Apple нативно).
- Напишіть нам і додайте файл BepInEx/LogOutput.log.

ВИДАЛЕННЯ
Очистіть Параметри запуску в Steam. За бажанням видаліть BepInEx, libdoorstop.dylib,
run_bepinex.sh, install_ua_macos.sh, .doorstop_version, changelog.txt
і doorstop_LICENSE.txt з папки гри.

ДЛЯ ПЕРЕКЛАДАЧІВ
- Переклад: BepInEx/plugins/DressmakerUA/translations/uk.json
- Шрифти: .ttf/.otf з кирилицею в BepInEx/plugins/DressmakerUA/fonts/ (default.ttf — для всього тексту).
  Без шрифтів використовується системний Georgia (BepInEx/config/ua.dressmaker.localization.cfg).

Використовується BepInEx 5 (https://github.com/BepInEx/BepInEx, LGPL-2.1)
і UnityDoorstop 4.6.0 (https://github.com/NeighTools/UnityDoorstop, LGPL-2.1).
