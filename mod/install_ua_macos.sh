#!/bin/sh
# Готує українізатор Dressmaker до запуску на macOS:
# знімає карантин macOS з файлів BepInEx і копіює рядок для «Параметрів запуску» Steam.
cd "$(dirname "$0")" || exit 1
if [ ! -d "Dressmaker.app" ]; then
    echo "Помилка: поруч із цим файлом немає Dressmaker.app."
    echo "Розпакуйте архів у папку гри (Steam → Dressmaker → Керування → Переглянути локальні файли)."
    exit 1
fi
xattr -dr com.apple.quarantine BepInEx libdoorstop.dylib run_bepinex.sh 2>/dev/null
chmod +x run_bepinex.sh
printf '"%s/run_bepinex.sh" %%command%%' "$PWD" | pbcopy
echo ""
echo "Готово! Рядок для Steam скопійовано в буфер обміну:"
echo ""
echo "    \"$PWD/run_bepinex.sh\" %command%"
echo ""
echo "Тепер: Steam → ПКМ на Dressmaker → Властивості → Загальні → Параметри запуску → Cmd+V."
