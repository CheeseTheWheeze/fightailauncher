using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

namespace FightingOverlay.Desktop;

public record UpdateInfo(string Version, string DownloadUrl);

public class UpdateService
{
    private const string LatestReleaseUrl = "https://api.github.com/repos/CheeseTheWheeze/fightailauncher/releases/latest";
    private const string AssetName = "FightAILauncher-Windows.zip";

    private readonly HttpClient _httpClient = new();

    public UpdateService()
    {
        _httpClient.DefaultRequestHeaders.UserAgent.ParseAdd("FightAILauncher");
    }

    public async Task<UpdateInfo?> CheckForUpdateAsync()
    {
        using var response = await _httpClient.GetAsync(LatestReleaseUrl);
        response.EnsureSuccessStatusCode();

        await using var stream = await response.Content.ReadAsStreamAsync();
        using var doc = await JsonDocument.ParseAsync(stream);
        var root = doc.RootElement;

        if (!root.TryGetProperty("tag_name", out var tagName))
        {
            return null;
        }

        var version = tagName.GetString();
        if (string.IsNullOrWhiteSpace(version))
        {
            return null;
        }

        var currentVersion = VersionInfo.ReadVersion();
        if (string.Equals(currentVersion, version, StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        if (!root.TryGetProperty("assets", out var assets))
        {
            return null;
        }

        foreach (var asset in assets.EnumerateArray())
        {
            if (asset.TryGetProperty("name", out var nameProp) &&
                nameProp.GetString() == AssetName &&
                asset.TryGetProperty("browser_download_url", out var urlProp))
            {
                var url = urlProp.GetString();
                if (!string.IsNullOrWhiteSpace(url))
                {
                    return new UpdateInfo(version, url);
                }
            }
        }

        return null;
    }

    public async Task<string> DownloadAndStageAsync(UpdateInfo update)
    {
        var updatesDir = Path.Combine(AppPaths.UpdatesDir(), update.Version);
        Directory.CreateDirectory(updatesDir);
        var zipPath = Path.Combine(updatesDir, AssetName);

        using var response = await _httpClient.GetAsync(update.DownloadUrl);
        response.EnsureSuccessStatusCode();
        await using (var output = File.Open(zipPath, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            await response.Content.CopyToAsync(output);
        }

        var versionDir = Path.Combine(AppPaths.VersionsDir(), update.Version);
        if (Directory.Exists(versionDir))
        {
            Directory.Delete(versionDir, recursive: true);
        }
        Directory.CreateDirectory(versionDir);
        ZipFile.ExtractToDirectory(zipPath, versionDir);

        var latestPath = Path.Combine(AppPaths.VersionsDir(), "latest.txt");
        File.WriteAllText(latestPath, update.Version);

        return CreateUpdaterScript(update.Version);
    }

    public void ApplyUpdateAndRestart(string scriptPath)
    {
        var currentPid = Process.GetCurrentProcess().Id;
        Process.Start(new ProcessStartInfo
        {
            FileName = "cmd.exe",
            Arguments = $"/c \"{scriptPath}\" {currentPid}",
            CreateNoWindow = true,
            UseShellExecute = false
        });
    }

    private string CreateUpdaterScript(string version)
    {
        var updatesDir = Path.Combine(AppPaths.UpdatesDir(), version);
        Directory.CreateDirectory(updatesDir);
        var scriptPath = Path.Combine(updatesDir, "apply_update.cmd");
        var logPath = Path.Combine(updatesDir, "update.log");

        var current = AppPaths.CurrentDir();
        var target = Path.Combine(AppPaths.VersionsDir(), version);
        var appExe = Path.Combine(current, "FightAILauncher.exe");

        var script = $@"@echo off
setlocal
set PID=%1
echo %DATE% %TIME% Starting update > ""{logPath}""
:wait
tasklist /FI ""PID eq %PID%"" | find ""%PID%"" >nul
if %errorlevel%==0 (
  timeout /t 1 >nul
  goto wait
)
if exist ""{current}"" (
  rmdir /S /Q ""{current}""
)
mklink /J ""{current}"" ""{target}""
if %errorlevel% neq 0 (
  echo mklink failed with %errorlevel% >> ""{logPath}""
  exit /b 1
)
start """" ""{appExe}""
";

        File.WriteAllText(scriptPath, script);
        return scriptPath;
    }
}
