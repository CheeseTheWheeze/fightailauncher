using System;
using System.Diagnostics;
using System.IO;

namespace FightingOverlay.Desktop;

public static class AppInstaller
{
    public static InstallResult EnsureInstalled()
    {
        try
        {
            var baseDir = Path.GetFullPath(AppDomain.CurrentDomain.BaseDirectory);
            var currentDir = Path.GetFullPath(AppPaths.CurrentDir());

            if (baseDir.StartsWith(currentDir + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            {
                return new InstallResult(false, false, null);
            }

            var version = VersionInfo.ReadVersion();
            var targetDir = Path.Combine(AppPaths.VersionsDir(), version);
            Directory.CreateDirectory(AppPaths.VersionsDir());

            if (!Directory.Exists(targetDir))
            {
                CopyDirectory(baseDir, targetDir);
            }

            var junctionResult = CreateJunction(AppPaths.CurrentDir(), targetDir);
            if (!junctionResult.Success)
            {
                return new InstallResult(true, false, junctionResult.ErrorMessage);
            }

            var exeName = Path.GetFileName(Process.GetCurrentProcess().MainModule?.FileName ?? "FightAILauncher.exe");
            var targetExe = Path.Combine(targetDir, exeName);
            if (!File.Exists(targetExe))
            {
                var message = $"Target executable not found at {targetExe}";
                Logger.Log(message);
                return new InstallResult(true, false, message);
            }

            try
            {
                var process = Process.Start(new ProcessStartInfo
                {
                    FileName = targetExe,
                    WorkingDirectory = targetDir,
                    UseShellExecute = true
                });
                if (process == null)
                {
                    var message = "Process.Start returned null during relaunch.";
                    Logger.Log(message);
                    return new InstallResult(true, false, message);
                }
            }
            catch (Exception ex)
            {
                Logger.Log($"Failed to relaunch: {ex}");
                return new InstallResult(true, false, ex.Message);
            }

            return new InstallResult(true, true, null);
        }
        catch (Exception ex)
        {
            Logger.Log($"EnsureInstalled failed: {ex}");
            return new InstallResult(true, false, ex.Message);
        }
    }

    private static JunctionResult CreateJunction(string junctionPath, string targetPath)
    {
        if (Directory.Exists(junctionPath))
        {
            try
            {
                Directory.Delete(junctionPath, recursive: true);
            }
            catch
            {
                Logger.Log($"Failed to delete existing junction at {junctionPath}.");
            }
        }

        var startInfo = new ProcessStartInfo
        {
            FileName = "cmd.exe",
            Arguments = $"/c mklink /J \"{junctionPath}\" \"{targetPath}\"",
            CreateNoWindow = true,
            UseShellExecute = false
        };
        using var process = Process.Start(startInfo);
        if (process == null)
        {
            var message = "Failed to start mklink process.";
            Logger.Log(message);
            return new JunctionResult(false, message);
        }

        process.WaitForExit();
        if (process.ExitCode != 0)
        {
            var message = $"mklink exited with code {process.ExitCode}.";
            Logger.Log(message);
            return new JunctionResult(false, message);
        }

        return new JunctionResult(true, null);
    }

    private static void CopyDirectory(string sourceDir, string targetDir)
    {
        Directory.CreateDirectory(targetDir);
        foreach (var file in Directory.GetFiles(sourceDir))
        {
            var destFile = Path.Combine(targetDir, Path.GetFileName(file));
            File.Copy(file, destFile, overwrite: true);
        }

        foreach (var directory in Directory.GetDirectories(sourceDir))
        {
            var destDir = Path.Combine(targetDir, Path.GetFileName(directory));
            CopyDirectory(directory, destDir);
        }
    }
}

public record InstallResult(bool DidInstallAttempt, bool RelaunchStarted, string? ErrorMessage);

public record JunctionResult(bool Success, string? ErrorMessage);
