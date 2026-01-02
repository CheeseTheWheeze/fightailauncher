using System;
using System.IO;
using System.Reflection;
using System.Text.Json;

namespace FightingOverlay.Desktop;

public static class VersionInfo
{
    public static string ReadVersion()
    {
        var versionPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "shared", "version.json");
        if (File.Exists(versionPath))
        {
            try
            {
                using var stream = File.OpenRead(versionPath);
                var doc = JsonDocument.Parse(stream);
                if (doc.RootElement.TryGetProperty("version", out var version))
                {
                    return version.GetString() ?? "unknown";
                }
            }
            catch
            {
            }
        }

        return Assembly.GetExecutingAssembly().GetName().Version?.ToString() ?? "unknown";
    }
}
