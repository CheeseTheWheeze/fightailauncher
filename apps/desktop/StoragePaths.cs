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

    public static string ProfilesDir() => Path.Combine(BaseDataDir(), "profiles");

    public static string LogsDir() => Path.Combine(BaseDataDir(), "logs");

    public static ClipPaths GetClipPaths(string athleteId, string clipId)
    {
        var profileDir = Path.Combine(ProfilesDir(), athleteId);
        var clipDir = Path.Combine(profileDir, "clips", clipId);
        return new ClipPaths(
            BaseDataDir(),
            profileDir,
            clipDir,
            Path.Combine(clipDir, "input"),
            Path.Combine(clipDir, "outputs"),
            Path.Combine(clipDir, "logs")
        );
    }
}

public record ClipPaths(
    string BaseDir,
    string ProfileDir,
    string ClipDir,
    string InputDir,
    string OutputsDir,
    string LogsDir
);
