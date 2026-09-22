using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using HarmonyLib;
using Newtonsoft.Json;
using TMPro;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.Localization;
using UnityEngine.Localization.Metadata;
using UnityEngine.Localization.Settings;
using UnityEngine.Localization.Tables;
using UnityEngine.ResourceManagement.AsyncOperations;
using UnityEngine.SceneManagement;
using UnityEngine.TextCore.LowLevel;

namespace DressmakerUA
{
    /// <summary>
    /// Українська локалізація Dressmaker.
    /// Додає мову "uk" у список мов гри, віддає для неї таблиці рядків з translations/uk.json
    /// (відсутні рядки — англійською) і підключає шрифт з кирилицею як запасний.
    /// Файли гри не змінюються.
    /// </summary>
    [BepInPlugin(Guid, "Dressmaker Ukrainian", Version)]
    public class Plugin : BaseUnityPlugin
    {
        public const string Guid = "ua.dressmaker.localization";
        public const string Version = "1.1.1";

        internal static ManualLogSource Log;
        internal static Plugin Instance;

        internal static ConfigEntry<string> LocaleCode;
        internal static ConfigEntry<string> DisplayName;
        internal static ConfigEntry<string> OsFontFallback;
        internal static ConfigEntry<bool> AutoSizeText;
        internal static ConfigEntry<float> AutoSizeMinRatio;

        // колекція ("UI", "Dialogue"...) -> id рядка -> переклад
        internal static Dictionary<string, Dictionary<long, string>> Translations =
            new Dictionary<string, Dictionary<long, string>>();

        internal static string PluginDir;

        private void Awake()
        {
            Instance = this;
            Log = Logger;
            PluginDir = Path.GetDirectoryName(Info.Location);

            LocaleCode = Config.Bind("General", "LocaleCode", "uk", "Код мови, під яким переклад додається в гру.");
            DisplayName = Config.Bind("General", "DisplayName", "Українська", "Назва мови в меню вибору мови.");
            OsFontFallback = Config.Bind("Fonts", "OsFontFallback", "Georgia",
                "Системний шрифт з кирилицею, якщо в папці fonts немає власних шрифтів.");
            AutoSizeText = Config.Bind("Fonts", "AutoSizeText", true,
                "Автоматично зменшувати текст, який не вміщається в кнопку чи напис "
                + "(українські слова довші за англійські).");
            AutoSizeMinRatio = Config.Bind("Fonts", "AutoSizeMinRatio", 0.6f,
                "Наскільки максимально дозволено зменшити текст: 0.6 = до 60% від авторського розміру.");

            LoadTranslations();

            LocalizationSettings.StringDatabase.TableProvider = new UkTableProvider();

            new Harmony(Guid).PatchAll(typeof(Patches));
            SceneManager.sceneLoaded += ScanScene;

            // якщо ініціалізація вже пройшла — додати мову зараз, інакше після неї
            var init = LocalizationSettings.InitializationOperation;
            if (init.IsDone) EnsureLocale(LocalizationSettings.AvailableLocales);
            else init.Completed += _ => EnsureLocale(LocalizationSettings.AvailableLocales);

            Log.LogInfo($"Завантажено перекладів: {Translations.Sum(t => t.Value.Count)} рядків у {Translations.Count} таблицях");
        }

        // ---------- текст, що не вміщається у вузькі кнопки ----------

        private static readonly HashSet<int> AutoSized = new HashSet<int>();

        /// <summary>
        /// Вмикає автомасштабування напису: якщо переклад не вміщається, TMP зменшить шрифт,
        /// замість того щоб рвати слово посередині. Авторський розмір лишається максимумом.
        /// </summary>
        internal static void ApplyAutoSize(TMP_Text text)
        {
            if (text == null || !AutoSizeText.Value || text.enableAutoSizing) return;
            if (!IsOurLocale(LocalizationSettings.SelectedLocale)) return;
            if (!AutoSized.Add(text.GetInstanceID())) return;
            float authored = text.fontSize;
            if (authored <= 0f) return;
            text.fontSizeMax = authored;
            text.fontSizeMin = Mathf.Max(6f, authored * Mathf.Clamp(AutoSizeMinRatio.Value, 0.2f, 1f));
            text.enableAutoSizing = true;
        }

        private static void ScanScene(Scene scene, LoadSceneMode mode)
        {
            foreach (var text in Resources.FindObjectsOfTypeAll<TMP_Text>())
                ApplyAutoSize(text);
        }

        private void LoadTranslations()
        {
            string path = Path.Combine(PluginDir, "translations", LocaleCode.Value + ".json");
            if (!File.Exists(path))
            {
                Log.LogError("Не знайдено файл перекладу: " + path);
                return;
            }
            try
            {
                var raw = JsonConvert.DeserializeObject<Dictionary<string, Dictionary<string, string>>>(
                    File.ReadAllText(path, System.Text.Encoding.UTF8));
                foreach (var table in raw)
                {
                    var dict = new Dictionary<long, string>();
                    foreach (var kv in table.Value)
                        if (long.TryParse(kv.Key, out long id)) dict[id] = kv.Value;
                    Translations[table.Key] = dict;
                }
            }
            catch (Exception e)
            {
                Log.LogError("Помилка читання " + path + ": " + e);
            }
        }

        internal static bool IsOurLocale(Locale locale) =>
            locale != null && locale.Identifier.Code == LocaleCode.Value;

        internal static void EnsureLocale(ILocalesProvider provider)
        {
            if (provider == null || provider.GetLocale(new LocaleIdentifier(LocaleCode.Value)) != null) return;
            var locale = Locale.CreateLocale(new LocaleIdentifier(LocaleCode.Value));
            locale.LocaleName = DisplayName.Value;
            locale.name = DisplayName.Value;
            // усе, чого немає в перекладі (картинки з текстом тощо), береться з англійської
            var en = provider.GetLocale(new LocaleIdentifier("en"));
            if (en != null) locale.Metadata.AddMetadata(new FallbackLocale(en));
            LocalizationSettings.AssetDatabase.UseFallback = true;
            UnityEngine.Object.DontDestroyOnLoad(locale);
            provider.AddLocale(locale);
            Log.LogInfo("Мову додано: " + LocaleCode.Value);
        }

        // ---------- таблиці ----------

        internal static StringTable BuildTable(StringTable en, string collection)
        {
            var table = ScriptableObject.CreateInstance<StringTable>();
            table.name = collection + "_" + LocaleCode.Value;
            table.LocaleIdentifier = new LocaleIdentifier(LocaleCode.Value);
            table.SharedData = en.SharedData;
            Translations.TryGetValue(collection, out var tr);
            int translated = 0;
            foreach (var entry in en.Values)
            {
                string text = entry.Value;
                if (tr != null && tr.TryGetValue(entry.KeyId, out var uk)) { text = uk; translated++; }
                var e = table.AddEntry(entry.KeyId, text);
                e.IsSmart = entry.IsSmart;
            }
            UnityEngine.Object.DontDestroyOnLoad(table);
            Log.LogInfo($"Таблиця {collection}: перекладено {translated} з {en.Count}");
            return table;
        }

        // ---------- шрифти ----------

        private static readonly Dictionary<string, TMP_FontAsset> FontCache = new Dictionary<string, TMP_FontAsset>();
        private static bool _fontsScanned;
        private static readonly Dictionary<string, string> FontFiles = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        /// <summary>
        /// Шрифт з кирилицею для оригінального шрифту гри.
        /// fonts/&lt;назва оригінального шрифту&gt;.ttf (напр. "EBGaramond-Medium SDF.ttf") — для конкретного шрифту,
        /// fonts/default.ttf — для решти; інакше системний шрифт з налаштувань.
        /// </summary>
        internal static TMP_FontAsset GetCyrillicFont(TMP_FontAsset latin)
        {
            ScanFonts();
            string key = latin != null && FontFiles.ContainsKey(latin.name) ? latin.name : "default";
            if (FontCache.TryGetValue(key, out var cached)) return cached;

            TMP_FontAsset font = null;
            try
            {
                if (FontFiles.TryGetValue(key, out var file))
                    font = TMP_FontAsset.CreateFontAsset(file, 0, 90, 9, GlyphRenderMode.SDFAA, 1024, 1024);
                if (font == null && key != "default")
                    font = GetCyrillicFont(null);
                if (font == null && !string.IsNullOrEmpty(OsFontFallback.Value))
                    font = TMP_FontAsset.CreateFontAsset(OsFontFallback.Value, "Regular");
            }
            catch (Exception e)
            {
                Log.LogError("Не вдалося створити шрифт для " + key + ": " + e);
            }
            if (font != null)
            {
                font.name = "UA fallback (" + key + ")";
                font.isMultiAtlasTexturesEnabled = true;
                UnityEngine.Object.DontDestroyOnLoad(font);
                Log.LogInfo("Шрифт з кирилицею для " + key + " готовий");
            }
            FontCache[key] = font;
            return font;
        }

        private static void ScanFonts()
        {
            if (_fontsScanned) return;
            _fontsScanned = true;
            string dir = Path.Combine(PluginDir, "fonts");
            if (!Directory.Exists(dir)) return;
            foreach (var f in Directory.GetFiles(dir))
            {
                string ext = Path.GetExtension(f).ToLowerInvariant();
                if (ext == ".ttf" || ext == ".otf")
                    FontFiles[Path.GetFileNameWithoutExtension(f)] = f;
            }
        }
    }

    /// <summary>Віддає таблиці для нашої мови, збудовані з англійських + переклад.</summary>
    internal class UkTableProvider : ITableProvider
    {
        public AsyncOperationHandle<TTable> ProvideTableAsync<TTable>(string tableCollectionName, Locale locale)
            where TTable : LocalizationTable
        {
            if (!Plugin.IsOurLocale(locale)) return default; // звичайне завантаження

            var rm = Addressables.ResourceManager;
            if (typeof(TTable) == typeof(StringTable))
            {
                var enHandle = Addressables.LoadAssetAsync<StringTable>(tableCollectionName + "_en");
                return rm.CreateChainOperation<TTable, StringTable>(enHandle, h =>
                {
                    if (h.Status != AsyncOperationStatus.Succeeded || h.Result == null)
                        return rm.CreateCompletedOperation<TTable>(null, "Не знайдено англійську таблицю " + tableCollectionName);
                    return rm.CreateCompletedOperation((TTable)(LocalizationTable)Plugin.BuildTable(h.Result, tableCollectionName), null);
                });
            }
            // таблиці ресурсів (картинки): таблиці немає -> гра візьме англійську через FallbackLocale
            return default;
        }
    }

    internal static class Patches
    {
        // мову треба додати до того, як гра вибере стартову мову із збережених налаштувань
        [HarmonyPatch(typeof(PlayerOptionsLocaleSelector), nameof(PlayerOptionsLocaleSelector.GetStartupLocale))]
        [HarmonyPrefix]
        private static void BeforeStartupLocale(ILocalesProvider availableLocales) => Plugin.EnsureLocale(availableLocales);

        // запасний шрифт з кирилицею для кожного шрифту гри
        [HarmonyPatch(typeof(LocaleFontFallbacks), nameof(LocaleFontFallbacks.Get))]
        [HarmonyPostfix]
        private static void FontFallback(TMP_FontAsset latin, Locale locale, ref TMP_FontAsset __result)
        {
            if (__result == null && latin != null && Plugin.IsOurLocale(locale))
                __result = Plugin.GetCyrillicFont(latin);
        }

        // написи, створені під час гри (кнопки в спливних вікнах тощо)
        [HarmonyPatch(typeof(TextMeshProUGUI), "OnEnable")]
        [HarmonyPostfix]
        private static void TextEnabled(TextMeshProUGUI __instance) => Plugin.ApplyAutoSize(__instance);

        // назва мови в меню
        [HarmonyPatch(typeof(LanguageSelectorPopup), "NativeName")]
        [HarmonyPostfix]
        private static void NativeName(Locale locale, ref string __result)
        {
            if (Plugin.IsOurLocale(locale)) __result = Plugin.DisplayName.Value;
        }
    }
}
