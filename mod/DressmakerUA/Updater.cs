using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.SceneManagement;

namespace DressmakerUA
{
    /// <summary>
    /// Автооновлення перекладу з релізів GitHub.
    /// Змінилась остання цифра версії (1.3.0 → 1.3.1) — оновився лише текст: uk.json з релізу
    /// завантажується в translations/uk.update.json і підхоплюється після перезапуску гри.
    /// Змінилась перша чи друга цифра (або файл вимагає новішого плагіна, поле minPlugin) —
    /// потрібен новий плагін: у головному меню з'являється напис з посиланням на реліз.
    /// </summary>
    internal static class Updater
    {
        private const string Repo = "nightsuperthunder/dressmaker-ua-localization";
        internal const string MetaKey = "_meta";

        internal static string UpdatePath =>
            Path.Combine(Plugin.PluginDir, "translations", Plugin.LocaleCode.Value + ".update.json");

        internal static bool TryParseVersion(string s, out Version v)
        {
            v = null;
            return !string.IsNullOrEmpty(s) && Version.TryParse(s.Trim().TrimStart('v', 'V'), out v);
        }

        internal static void Start()
        {
            if (!Plugin.AutoUpdate.Value) return;
            Get($"https://api.github.com/repos/{Repo}/releases/latest", OnRelease);
        }

        private static void Get(string url, Action<UnityWebRequest> done)
        {
            var req = UnityWebRequest.Get(url);
            req.timeout = 30;
            req.SetRequestHeader("Accept", "application/vnd.github+json");
            req.SendWebRequest().completed += _ =>
            {
                try
                {
                    if (req.result != UnityWebRequest.Result.Success)
                        Plugin.Log.LogInfo("Не вдалося перевірити оновлення: " + req.error);
                    else
                        done(req);
                }
                catch (Exception e)
                {
                    Plugin.Log.LogWarning("Помилка оновлення: " + e.Message);
                }
                finally
                {
                    req.Dispose();
                }
            };
        }

        private static void OnRelease(UnityWebRequest req)
        {
            var rel = JObject.Parse(req.downloadHandler.text);
            if (!TryParseVersion((string)rel["tag_name"], out var latest)) return;
            string page = (string)rel["html_url"];
            var plugin = Plugin.PluginVersion;

            // нова перша чи друга цифра — потрібен новий плагін, текст не чіпаємо
            if (latest.Major != plugin.Major || latest.Minor != plugin.Minor)
            {
                if (latest > plugin) Notice.ShowPluginUpdate(latest, page);
                return;
            }
            if (latest <= Plugin.TextVersion)
            {
                Plugin.Log.LogInfo($"Переклад актуальний ({Plugin.TextVersion})");
                return;
            }
            string name = Plugin.LocaleCode.Value + ".json";
            string url = rel["assets"]?.FirstOrDefault(a => (string)a["name"] == name)?["browser_download_url"]?.ToString();
            if (string.IsNullOrEmpty(url))
            {
                Plugin.Log.LogInfo($"У релізі {latest} немає файлу {name}");
                return;
            }
            Get(url, r => OnTranslations(r, latest, page));
        }

        private static void OnTranslations(UnityWebRequest req, Version latest, string page)
        {
            string json = Encoding.UTF8.GetString(req.downloadHandler.data);
            var raw = Plugin.ParseTranslations(json);
            var version = Plugin.MetaVersion(raw, "version");
            var minPlugin = Plugin.MetaVersion(raw, "minPlugin");
            if (version == null || version <= Plugin.TextVersion)
            {
                Plugin.Log.LogWarning("Завантажений переклад не новіший за поточний — пропускаю");
                return;
            }
            if (minPlugin != null && minPlugin > Plugin.PluginVersion)
            {
                Notice.ShowPluginUpdate(latest, page);
                return;
            }
            // захист від зламаного чи обрізаного файлу
            int count = Plugin.CountStrings(raw);
            int current = Plugin.Translations.Sum(t => t.Value.Count);
            if (count < current * 0.9)
            {
                Plugin.Log.LogWarning($"У завантаженому перекладі підозріло мало рядків ({count} проти {current}) — пропускаю");
                return;
            }

            string tmp = UpdatePath + ".tmp";
            File.WriteAllText(tmp, json, new UTF8Encoding(false));
            if (File.Exists(UpdatePath)) File.Delete(UpdatePath);
            File.Move(tmp, UpdatePath);
            Plugin.Log.LogInfo($"Завантажено переклад {version} ({count} рядків), діятиме після перезапуску гри");
            Notice.ShowTextUpdate(version);
        }
    }

    /// <summary>Напис про оновлення в головному меню (IMGUI поверх інтерфейсу гри).</summary>
    internal class Notice : MonoBehaviour
    {
        private const string SteamAppId = "4019220";
        private const string TitleScene = "TitleScreen";

        private static Notice _instance;
        private string _message, _action, _url;
        private bool _restart, _hidden;

        private static Notice Get()
        {
            if (_instance == null)
            {
                var go = new GameObject("DressmakerUA.Notice");
                go.hideFlags = HideFlags.HideAndDontSave;
                DontDestroyOnLoad(go);
                _instance = go.AddComponent<Notice>();
            }
            return _instance;
        }

        internal static void ShowTextUpdate(Version v)
        {
            var n = Get();
            n._message = $"Українізатор: тексти оновлено до версії {v}.\nЗміни з'являться після перезапуску гри.";
            n._action = "Перезапустити";
            n._restart = true;
        }

        internal static void ShowPluginUpdate(Version v, string url)
        {
            var n = Get();
            n._message = $"Вийшла нова версія українізатора ({v}).\nЇї треба встановити вручну.";
            n._action = "Завантажити";
            n._url = url;
            n._restart = false;
        }

        private void OnGUI()
        {
            if (_message == null || _hidden || SceneManager.GetActiveScene().name != TitleScene) return;

            float s = Screen.height / 1080f;
            float w = 520 * s, h = 150 * s, m = 20 * s;
            var rect = new Rect(Screen.width - w - m, m, w, h);
            var box = new GUIStyle(GUI.skin.box)
            {
                fontSize = Mathf.RoundToInt(22 * s),
                wordWrap = true,
                alignment = TextAnchor.UpperCenter,
                padding = new RectOffset((int)m, (int)m, (int)m, (int)m),
            };
            box.normal.textColor = Color.white;
            var button = new GUIStyle(GUI.skin.button) { fontSize = Mathf.RoundToInt(20 * s) };

            // двічі — щоб напівпрозорий фон став темнішим і текст читався на будь-якому тлі
            GUI.Box(rect, GUIContent.none, box);
            GUI.Box(rect, _message, box);

            float bw = (w - 3 * m) / 2, bh = 44 * s, by = rect.yMax - bh - m;
            if (GUI.Button(new Rect(rect.x + m, by, bw, bh), _action, button))
            {
                if (_restart) Restart();
                else if (!string.IsNullOrEmpty(_url)) Application.OpenURL(_url);
                _hidden = true;
            }
            if (GUI.Button(new Rect(rect.x + 2 * m + bw, by, bw, bh), _restart ? "Пізніше" : "Закрити", button))
                _hidden = true;
        }

        /// <summary>
        /// Перезапуск через Steam: гра закривається, а через кілька секунд окремий процес
        /// просить Steam запустити її знову (одразу Steam вважав би, що гра ще працює).
        /// </summary>
        private static void Restart()
        {
            try
            {
                string url = "steam://rungameid/" + SteamAppId;
                bool mac = Application.platform == RuntimePlatform.OSXPlayer;
                // на macOS Steam сам підставить параметри запуску (run_bepinex.sh %command%)
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
                {
                    FileName = mac ? "/bin/sh" : "cmd.exe",
                    Arguments = mac
                        ? $"-c \"sleep 5; open '{url}'\""
                        : $"/c ping -n 6 127.0.0.1 >nul & start \"\" {url}",
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden,
                });
            }
            catch (Exception e)
            {
                Plugin.Log.LogWarning("Не вдалося запланувати перезапуск: " + e.Message);
            }
            Application.Quit();
        }
    }
}
