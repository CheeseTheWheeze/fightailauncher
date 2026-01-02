using System;
using System.Diagnostics;
using System.IO;

namespace FightingOverlay.Desktop;

public static class Logger
{
    private static readonly string LogDirectoryPath = StoragePaths.LogsDir();
    private static readonly string LogFilePath = Path.Combine(LogDirectoryPath, "desktop.log");

    public static string LogDirectory => LogDirectoryPath;

    public static string LogFile => LogFilePath;

    public static void Log(string message)
    {
        try
        {
            Directory.CreateDirectory(LogDirectoryPath);
            File.AppendAllText(LogFilePath, $"{DateTime.UtcNow:O} {message}{Environment.NewLine}");
        }
        catch
        {
        }
    }

    public static void OpenLogsFolder()
    {
        try
        {
            Directory.CreateDirectory(LogDirectoryPath);
            Process.Start(new ProcessStartInfo("explorer.exe", LogDirectoryPath) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            Log($"Failed to open logs folder: {ex.Message}");
        }
    }
}
