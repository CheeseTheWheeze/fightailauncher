using System;
using System.IO;

namespace FightingOverlay.Desktop;

public static class StoragePaths
{
    private const string AppName = "FightingOverlay";

    public static string BaseDataDir()
    {
        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        return Path.Combine(localAppData, AppName, "data");
    }

    public static string RunsDir() => Path.Combine(BaseDataDir(), "runs");

    public static string LogsDir() => Path.Combine(BaseDataDir(), "logs");

    public static RunPaths GetRunPaths(string runId)
    {
        var runDir = Path.Combine(RunsDir(), runId);
        return new RunPaths(
            BaseDataDir(),
            runDir,
            Path.Combine(runDir, "input"),
            Path.Combine(runDir, "outputs"),
            Path.Combine(runDir, "logs")
        );
    }
}

public record RunPaths(
    string BaseDir,
    string RunDir,
    string InputDir,
    string OutputsDir,
    string LogsDir
);
