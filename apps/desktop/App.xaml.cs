using System;
using System.Windows;

namespace FightingOverlay.Desktop;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        try
        {
            if (Array.Exists(e.Args, arg => string.Equals(arg, "--ui-smoke-test", StringComparison.OrdinalIgnoreCase)))
            {
                Logger.Log("UI smoke test requested. Exiting after initialization.");
                Shutdown(0);
                return;
            }

            if (Array.Exists(e.Args, arg => string.Equals(arg, "--installed-run", StringComparison.OrdinalIgnoreCase)))
            {
                Logger.Log("Skipping EnsureInstalled due to --installed-run flag.");
            }
            else
            {
                var result = AppInstaller.EnsureInstalled();
                if (result.RelaunchStarted)
                {
                    Shutdown();
                    return;
                }

                if (!string.IsNullOrWhiteSpace(result.ErrorMessage))
                {
                    Logger.Log($"Startup install/relaunch failed: {result.ErrorMessage}");
                    ShowStartupError($"Install/relaunch failed: {result.ErrorMessage}");
                }
            }
        }
        catch (Exception ex)
        {
            Logger.Log($"Startup failed: {ex}");
            ShowStartupError($"Startup failed: {ex.Message}");
        }

        var mainWindow = new MainWindow();
        mainWindow.Show();
    }

    private static void ShowStartupError(string message)
    {
        var result = MessageBox.Show(
            $"{message}\n\nWould you like to open the logs folder?",
            "Startup Warning",
            MessageBoxButton.YesNo,
            MessageBoxImage.Warning);
        if (result == MessageBoxResult.Yes)
        {
            Logger.OpenLogsFolder();
        }
    }
}
