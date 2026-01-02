using Microsoft.Win32;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;

namespace FightingOverlay.Desktop;

public partial class MainWindow : Window
{
    private string? _lastOutputDir;
    private string? _lastLogsDir;
    private string? _lastEngineVersion;
    private readonly UpdateService _updateService = new();

    public MainWindow()
    {
        InitializeComponent();
        Directory.CreateDirectory(StoragePaths.BaseDataDir());
        Directory.CreateDirectory(StoragePaths.LogsDir());
        Directory.CreateDirectory(StoragePaths.RunsDir());
        LoadRunHistory();
        LoadVersion();
        LoadDiagnostics();
    }

    private void LoadRunHistory()
    {
        RunHistoryList.Items.Clear();
        var runsDir = StoragePaths.RunsDir();
        Directory.CreateDirectory(runsDir);

        var runDirs = Directory.EnumerateDirectories(runsDir)
            .OrderByDescending(path => Directory.GetCreationTimeUtc(path))
            .Take(10);

        foreach (var runDir in runDirs)
        {
            var resultPath = Path.Combine(runDir, "outputs", "result.json");
            if (!File.Exists(resultPath))
            {
                continue;
            }

            try
            {
                var json = File.ReadAllText(resultPath);
                var result = EngineRunResult.FromJson(json);
                var display = $"{Path.GetFileName(runDir)} - {result.Status}";
                RunHistoryList.Items.Add(display);
            }
            catch (Exception ex)
            {
                AppendLog($"Failed to load run history: {ex.Message}");
            }
        }
    }

    private void LoadVersion()
    {
        try
        {
            VersionText.Text = $"Version {VersionInfo.ReadVersion()}";
        }
        catch (Exception ex)
        {
            AppendLog($"Failed to read version: {ex.Message}");
        }
    }

    private void LoadDiagnostics()
    {
        try
        {
            AppVersionText.Text = $"App version: {VersionInfo.ReadVersion()}";
        }
        catch (Exception ex)
        {
            AppendLog($"Failed to read app version: {ex.Message}");
        }

        BaseDirText.Text = $"Running from: {AppDomain.CurrentDomain.BaseDirectory}";
        InstalledDirText.Text = $"Installed current dir: {AppPaths.CurrentDir()}";
        LatestVersionText.Text = $"Latest pointer: {ReadLatestVersion()}";
        EnginePathText.Text = $"Engine path attempted: {EngineLocator.GetAttemptedEnginePath()}";
        OutputDirText.Text = "Output folder: (none yet)";
        EngineVersionText.Text = "Engine version: unknown";
    }

    private static string ReadLatestVersion()
    {
        try
        {
            var latestPath = Path.Combine(AppPaths.VersionsDir(), "latest.txt");
            if (File.Exists(latestPath))
            {
                return File.ReadAllText(latestPath).Trim();
            }
        }
        catch
        {
        }

        return "unknown";
    }

    private void OnBrowseVideo(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Filter = "Video Files|*.mp4;*.mov;*.avi|All Files|*.*"
        };
        if (dialog.ShowDialog() == true)
        {
            VideoPathTextBox.Text = dialog.FileName;
        }
    }

    private async void OnAnalyze(object sender, RoutedEventArgs e)
    {
        var videoPath = VideoPathTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(videoPath))
        {
            MessageBox.Show("Please select a video file.");
            return;
        }

        var runId = Guid.NewGuid().ToString("N");
        var runPaths = StoragePaths.GetRunPaths(runId);
        Directory.CreateDirectory(runPaths.InputDir);
        Directory.CreateDirectory(runPaths.OutputsDir);
        Directory.CreateDirectory(runPaths.LogsDir);

        _lastOutputDir = runPaths.OutputsDir;
        _lastLogsDir = runPaths.LogsDir;
        OpenOutputButton.IsEnabled = false;
        OverlayStatusText.Text = string.Empty;
        OutputDirText.Text = $"Output folder: {runPaths.OutputsDir}";
        AppendLog($"Starting analysis for run {runId}");

        var engineInfo = EngineLocator.ResolveEngine();
        if (engineInfo == null)
        {
            Logger.Log("Engine not found. Set FIGHTING_OVERLAY_ENGINE_PATH or install engine.");
            ShowEngineMissingDialog();
            return;
        }
        EnginePathText.Text = $"Engine path attempted: {engineInfo.EnginePath}";
        var runner = new EngineRunner(engineInfo);
        EngineRunResult result;
        try
        {
            result = await runner.RunAnalyzeAsync(videoPath, runId, AppendLog);
        }
        catch (Exception ex)
        {
            Logger.Log($"Analyze failed: {ex}");
            MessageBox.Show($"Analyze failed: {ex.Message}");
            return;
        }

        _lastEngineVersion = result.Version ?? "unknown";
        EngineVersionText.Text = $"Engine version: {_lastEngineVersion}";

        LoadRunHistory();

        if (result.Status == "ok")
        {
            OpenOutputButton.IsEnabled = true;
            var overlayPath = result.ResolveOverlayPath(runPaths.OutputsDir);
            if (!string.IsNullOrWhiteSpace(overlayPath))
            {
                var loaded = await TryLoadOverlayAsync(overlayPath);
                if (!loaded)
                {
                    OverlayStatusText.Text = "Overlay preview failed to load. Use Open Output Folder to review files.";
                    OpenOutputButton.IsEnabled = true;
                }
            }
            else
            {
                AppendLog("Overlay path missing in result.json.");
                OverlayStatusText.Text = "Overlay preview missing. Use Open Output Folder to review files.";
                OpenOutputButton.IsEnabled = true;
            }
        }
        else
        {
            ShowEngineError(result, runPaths.OutputsDir, runPaths.LogsDir);
        }
    }

    private async void OnUpdate(object sender, RoutedEventArgs e)
    {
        UpdateButton.IsEnabled = false;
        try
        {
            AppendLog("Checking for updates...");
            var update = await _updateService.CheckForUpdateAsync();
            if (update == null)
            {
                AppendLog("No update available.");
                MessageBox.Show("You're already on the latest version.");
                return;
            }

            AppendLog($"Downloading update {update.Version}...");
            var scriptPath = await _updateService.DownloadAndStageAsync(update);
            AppendLog("Update staged. Restarting to apply update...");
            _updateService.ApplyUpdateAndRestart(scriptPath);
            Application.Current.Shutdown();
        }
        catch (Exception ex)
        {
            AppendLog($"Update failed: {ex.Message}");
            MessageBox.Show($"Update failed: {ex.Message}");
        }
        finally
        {
            UpdateButton.IsEnabled = true;
        }
    }

    private async Task<bool> TryLoadOverlayAsync(string overlayPath)
    {
        if (!File.Exists(overlayPath))
        {
            AppendLog("Overlay video not found.");
            return false;
        }

        var fileInfo = new FileInfo(overlayPath);
        var sizeBefore = fileInfo.Length;
        await Task.Delay(500);
        fileInfo.Refresh();
        var sizeAfter = fileInfo.Length;
        var isStable = sizeBefore == sizeAfter && sizeAfter > 0;
        AppendLog($"Overlay file exists at {overlayPath} size={sizeAfter} stable={isStable}");
        if (!isStable)
        {
            return false;
        }

        LoadOverlay(overlayPath);
        return true;
    }

    private void LoadOverlay(string overlayPath)
    {
        PreviewPlayer.Stop();
        PreviewPlayer.Source = null;
        PreviewPlayer.Source = new Uri(overlayPath);
        PreviewPlayer.Play();
        OverlayStatusText.Text = string.Empty;
        AppendLog("Overlay loaded.");
    }

    private void OnOpenOutput(object sender, RoutedEventArgs e)
    {
        if (_lastOutputDir == null)
        {
            MessageBox.Show("No output folder available yet.");
            return;
        }
        Process.Start(new ProcessStartInfo("explorer.exe", _lastOutputDir) { UseShellExecute = true });
    }

    private void OnOpenLogs(object sender, RoutedEventArgs e)
    {
        var logsDir = _lastLogsDir ?? Logger.LogDirectory;
        Process.Start(new ProcessStartInfo("explorer.exe", logsDir) { UseShellExecute = true });
    }

    private void AppendLog(string message)
    {
        Dispatcher.Invoke(() =>
        {
            LogTextBox.AppendText(message + Environment.NewLine);
            LogTextBox.ScrollToEnd();
        });
        Logger.Log(message);
    }

    private void ShowEngineMissingDialog()
    {
        var result = MessageBox.Show(
            "Engine not found. The UI will stay open, but analysis cannot run.\n\nYes = Open Logs Folder\nNo = Open App Folder",
            "Engine Missing",
            MessageBoxButton.YesNoCancel,
            MessageBoxImage.Error);

        if (result == MessageBoxResult.Yes)
        {
            Logger.OpenLogsFolder();
        }
        else if (result == MessageBoxResult.No)
        {
            Process.Start(new ProcessStartInfo("explorer.exe", AppDomain.CurrentDomain.BaseDirectory) { UseShellExecute = true });
        }
    }

    private void ShowEngineError(EngineRunResult result, string outputDir, string logsDir)
    {
        var errorMessage = result.Error?.Message ?? "Engine failed with an unknown error.";
        var hint = result.Error?.Hint;
        var code = result.Error?.Code;
        var message = $"{errorMessage}";

        if (!string.IsNullOrWhiteSpace(code))
        {
            message += $"\n\nError code: {code}";
        }

        if (!string.IsNullOrWhiteSpace(hint))
        {
            message += $"\nHint: {hint}";
        }

        message += "\n\nYes = Open Logs\nNo = Open Output Folder\nCancel = OK";

        var resultChoice = MessageBox.Show(
            message,
            "Analysis Error",
            MessageBoxButton.YesNoCancel,
            MessageBoxImage.Error);

        if (resultChoice == MessageBoxResult.Yes)
        {
            Process.Start(new ProcessStartInfo("explorer.exe", logsDir) { UseShellExecute = true });
        }
        else if (resultChoice == MessageBoxResult.No)
        {
            Process.Start(new ProcessStartInfo("explorer.exe", outputDir) { UseShellExecute = true });
        }
    }
}

public static class EngineLocator
{
    public static EngineInfo? ResolveEngine()
    {
        var envPath = Environment.GetEnvironmentVariable("FIGHTING_OVERLAY_ENGINE_PATH");
        if (!string.IsNullOrWhiteSpace(envPath) && File.Exists(envPath))
        {
            return new EngineInfo(envPath);
        }

        var baseDir = AppDomain.CurrentDomain.BaseDirectory;
        var exePath = Path.Combine(baseDir, "engine", "engine.exe");
        if (File.Exists(exePath))
        {
            return new EngineInfo(exePath);
        }

        return null;
    }

    public static string GetAttemptedEnginePath()
    {
        var envPath = Environment.GetEnvironmentVariable("FIGHTING_OVERLAY_ENGINE_PATH");
        if (!string.IsNullOrWhiteSpace(envPath))
        {
            return envPath;
        }

        var baseDir = AppDomain.CurrentDomain.BaseDirectory;
        return Path.Combine(baseDir, "engine", "engine.exe");
    }
}

public record EngineInfo(string EnginePath);
