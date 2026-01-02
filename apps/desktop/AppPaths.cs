using System;
using System.IO;

namespace FightingOverlay.Desktop;

public static class AppPaths
{
    private const string AppName = "FightingOverlay";

    public static string LocalAppData()
        => Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);

    public static string AppRoot()
        => Path.Combine(LocalAppData(), AppName, "app");

    public static string CurrentDir()
        => Path.Combine(AppRoot(), "current");

    public static string VersionsDir()
        => Path.Combine(AppRoot(), "versions");

    public static string UpdatesDir()
        => Path.Combine(StoragePaths.BaseDataDir(), "updates");
}
