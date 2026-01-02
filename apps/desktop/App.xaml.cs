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
            var result = AppInstaller.EnsureInstalled();
            if (result.RelaunchStarted)
            {
                Shutdown();
                return;
            }

            if (!string.IsNullOrWhiteSpace(result.ErrorMessage))
            {
                DesktopLogger.Log($"Startup install/relaunch failed: {result.ErrorMessage}");
                ShowStartupError($"Install/relaunch failed: {result.ErrorMessage}");
            }
        }
        catch (Exception ex)
        {
            DesktopLogger.Log($"Startup failed: {ex}");
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
            DesktopLogger.OpenLogsFolder();
        }
    }
}
