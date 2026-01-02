using System;
using System.Diagnostics;
using System.IO;

namespace FightingOverlay.Desktop;

public static class AppInstaller
{
    public static bool EnsureInstalled()
    {
        var baseDir = Path.GetFullPath(AppDomain.CurrentDomain.BaseDirectory);
        var currentDir = Path.GetFullPath(AppPaths.CurrentDir());

        if (baseDir.StartsWith(currentDir + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        var version = VersionInfo.ReadVersion();
        var targetDir = Path.Combine(AppPaths.VersionsDir(), version);
        Directory.CreateDirectory(AppPaths.VersionsDir());

        if (!Directory.Exists(targetDir))
        {
            CopyDirectory(baseDir, targetDir);
        }

        CreateJunction(AppPaths.CurrentDir(), targetDir);

        var exeName = Path.GetFileName(Process.GetCurrentProcess().MainModule?.FileName ?? "FightAILauncher.exe");
        var targetExe = Path.Combine(targetDir, exeName);
        Process.Start(new ProcessStartInfo
        {
            FileName = targetExe,
            WorkingDirectory = targetDir,
            UseShellExecute = true
        });

        return true;
    }

    private static void CreateJunction(string junctionPath, string targetPath)
    {
        if (Directory.Exists(junctionPath))
        {
            Directory.Delete(junctionPath);
        }

        var startInfo = new ProcessStartInfo
        {
            FileName = "cmd.exe",
            Arguments = $"/c mklink /J \"{junctionPath}\" \"{targetPath}\"",
            CreateNoWindow = true,
            UseShellExecute = false
        };
        using var process = Process.Start(startInfo);
        process?.WaitForExit();
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
