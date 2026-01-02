using System;
using System.Diagnostics;
using System.IO;

namespace FightingOverlay.Desktop;

public static class AppInstaller
{
    private static readonly TimeSpan InstallFailureBackoff = TimeSpan.FromHours(24);

    public static InstallResult EnsureInstalled()
    {
        try
        {
            var exePath = Process.GetCurrentProcess().MainModule?.FileName;
            if (string.IsNullOrWhiteSpace(exePath))
            {
                return new InstallResult(true, false, "Unable to determine exe path");
            }

            var runDir = Path.GetFullPath(Path.GetDirectoryName(exePath)!);
            var currentDir = Path.GetFullPath(AppPaths.CurrentDir());
            var versionsDir = Path.GetFullPath(AppPaths.VersionsDir());

            var currentPrefix = currentDir.EndsWith(Path.DirectorySeparatorChar)
                ? currentDir
                : currentDir + Path.DirectorySeparatorChar;
            var versionsPrefix = versionsDir.EndsWith(Path.DirectorySeparatorChar)
                ? versionsDir
                : versionsDir + Path.DirectorySeparatorChar;

            if (string.Equals(runDir, currentDir, StringComparison.OrdinalIgnoreCase) ||
                runDir.StartsWith(currentPrefix, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(runDir, versionsDir, StringComparison.OrdinalIgnoreCase) ||
                runDir.StartsWith(versionsPrefix, StringComparison.OrdinalIgnoreCase))
            {
                return new InstallResult(false, false, null);
            }

            var failureMarker = Path.Combine(AppPaths.AppRoot(), "install_failed.txt");
            if (File.Exists(failureMarker))
            {
                var lastWrite = File.GetLastWriteTimeUtc(failureMarker);
                if (DateTime.UtcNow - lastWrite <= InstallFailureBackoff)
                {
                    Logger.Log("Skipping install due to prior failure marker.");
                    return new InstallResult(false, false, null);
                }
            }

            var version = VersionInfo.ReadVersion();
            var targetDir = Path.Combine(AppPaths.VersionsDir(), version);
            Directory.CreateDirectory(AppPaths.VersionsDir());

            if (!Directory.Exists(targetDir))
            {
                CopyDirectory(runDir, targetDir);
            }

            var junctionResult = CreateJunction(AppPaths.CurrentDir(), targetDir);
            if (!junctionResult.Success)
            {
                Directory.CreateDirectory(AppPaths.AppRoot());
                File.WriteAllText(
                    failureMarker,
                    $"{DateTime.UtcNow:O} {junctionResult.ErrorMessage ?? "Unknown error"}");
                return new InstallResult(true, false, junctionResult.ErrorMessage);
            }

            if (File.Exists(failureMarker))
            {
                File.Delete(failureMarker);
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
                    Arguments = "--installed-run",
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
            var removeInfo = new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = $"/c rmdir /S /Q \"{junctionPath}\"",
                CreateNoWindow = true,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };
            using var removeProcess = Process.Start(removeInfo);
            if (removeProcess != null)
            {
                removeProcess.WaitForExit();
                var removeOut = removeProcess.StandardOutput.ReadToEnd();
                var removeErr = removeProcess.StandardError.ReadToEnd();
                if (!string.IsNullOrWhiteSpace(removeOut))
                {
                    Logger.Log($"rmdir output: {removeOut}");
                }
                if (!string.IsNullOrWhiteSpace(removeErr))
                {
                    Logger.Log($"rmdir error: {removeErr}");
                }
                if (removeProcess.ExitCode != 0)
                {
                    Logger.Log($"rmdir exited with code {removeProcess.ExitCode}.");
                }
            }

            if (Directory.Exists(junctionPath))
            {
                var timestamp = DateTime.UtcNow.ToString("yyyyMMddHHmmss");
                var backupPath = $"{junctionPath}_old_{timestamp}";
                try
                {
                    Directory.Move(junctionPath, backupPath);
                    Logger.Log($"Renamed existing junction to {backupPath}.");
                }
                catch (Exception ex)
                {
                    Logger.Log($"Failed to rename existing junction at {junctionPath}: {ex.Message}");
                }
            }
        }

        var startInfo = new ProcessStartInfo
        {
            FileName = "cmd.exe",
            Arguments = $"/c mklink /J \"{junctionPath}\" \"{targetPath}\"",
            CreateNoWindow = true,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        using var process = Process.Start(startInfo);
        if (process == null)
        {
            var message = "Failed to start mklink process.";
            Logger.Log(message);
            return new JunctionResult(false, message);
        }

        process.WaitForExit();
        var stdOut = process.StandardOutput.ReadToEnd();
        var stdErr = process.StandardError.ReadToEnd();
        if (!string.IsNullOrWhiteSpace(stdOut))
        {
            Logger.Log($"mklink output: {stdOut}");
        }
        if (!string.IsNullOrWhiteSpace(stdErr))
        {
            Logger.Log($"mklink error: {stdErr}");
        }
        if (process.ExitCode != 0)
        {
            var message = $"mklink exited with code {process.ExitCode}. {stdErr}".Trim();
            Logger.Log(message);
            return new JunctionResult(false, message);
        }

        if (!Directory.Exists(junctionPath))
        {
            var message = "mklink reported success but junction path was not created.";
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
