using Microsoft.Win32;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Windows;

namespace FightingOverlay.Desktop;

public partial class MainWindow : Window
{
    private readonly string _desktopLogPath;
    private string? _lastOutputDir;
    private string? _lastLogsDir;
    private readonly UpdateService _updateService = new();

    public MainWindow()
    {
        InitializeComponent();
        Directory.CreateDirectory(StoragePaths.BaseDataDir());
        Directory.CreateDirectory(StoragePaths.LogsDir());
        _desktopLogPath = Path.Combine(StoragePaths.LogsDir(), "desktop.log");
        LoadProfiles();
        LoadVersion();
    }

    private void LoadProfiles()
    {
        ProfileComboBox.Items.Clear();
        var profilesDir = StoragePaths.ProfilesDir();
        Directory.CreateDirectory(profilesDir);
        foreach (var profilePath in Directory.EnumerateFiles(profilesDir, "profile.json", SearchOption.AllDirectories))
        {
            try
            {
                var json = File.ReadAllText(profilePath);
                var profile = JsonSerializer.Deserialize<ProfileRecord>(json);
                if (profile != null)
                {
                    ProfileComboBox.Items.Add(new ProfileItem(profile.id, profile.name));
                }
            }
            catch (Exception ex)
            {
                AppendLog($"Failed to load profile: {ex.Message}");
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

    private void OnNewProfile(object sender, RoutedEventArgs e)
    {
        var name = Microsoft.VisualBasic.Interaction.InputBox("Enter athlete name", "New Profile", "Athlete");
        if (string.IsNullOrWhiteSpace(name))
        {
            return;
        }

        var athleteId = Guid.NewGuid().ToString("N");
        var profileDir = Path.Combine(StoragePaths.ProfilesDir(), athleteId);
        Directory.CreateDirectory(profileDir);
        var profile = new ProfileRecord(athleteId, name, DateTime.UtcNow.ToString("O"));
        File.WriteAllText(Path.Combine(profileDir, "profile.json"), JsonSerializer.Serialize(profile, new JsonSerializerOptions { WriteIndented = true }));
        LoadProfiles();
        ProfileComboBox.SelectedItem = ProfileComboBox.Items.OfType<ProfileItem>().FirstOrDefault(item => item.Id == athleteId);
    }

    private async void OnAnalyze(object sender, RoutedEventArgs e)
    {
        var videoPath = VideoPathTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(videoPath) || !File.Exists(videoPath))
        {
            MessageBox.Show("Please select a valid video file.");
            return;
        }

        if (ProfileComboBox.SelectedItem is not ProfileItem profile)
        {
            MessageBox.Show("Please select an athlete profile.");
            return;
        }

        var clipId = Guid.NewGuid().ToString("N");
        var clipPaths = StoragePaths.GetClipPaths(profile.Id, clipId);
        Directory.CreateDirectory(clipPaths.InputDir);
        Directory.CreateDirectory(clipPaths.OutputsDir);
        Directory.CreateDirectory(clipPaths.LogsDir);

        _lastOutputDir = clipPaths.OutputsDir;
        _lastLogsDir = clipPaths.LogsDir;
        AppendLog($"Starting analysis for {profile.Name} (clip {clipId})");

        var engineInfo = EngineLocator.ResolveEngine();
        if (engineInfo == null)
        {
            MessageBox.Show("Engine not found. Set FIGHTING_OVERLAY_ENGINE_PATH.");
            return;
        }

        var args = new StringBuilder();
        args.Append("analyze ");
        args.Append($"--video \"{videoPath}\" ");
        args.Append($"--athlete {profile.Id} ");
        args.Append($"--clip {clipId} ");
        args.Append($"--outdir \"{clipPaths.OutputsDir}\"");

        var startInfo = new ProcessStartInfo
        {
            FileName = engineInfo.EnginePath,
            Arguments = args.ToString(),
            WorkingDirectory = AppDomain.CurrentDomain.BaseDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };

        using var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
        process.OutputDataReceived += (_, eventArgs) =>
        {
            if (eventArgs.Data != null)
            {
                AppendLog(eventArgs.Data);
            }
        };
        process.ErrorDataReceived += (_, eventArgs) =>
        {
            if (eventArgs.Data != null)
            {
                AppendLog($"ERR: {eventArgs.Data}");
            }
        };

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        await process.WaitForExitAsync();
        AppendLog($"Engine exited with code {process.ExitCode}");

        var resultPath = Path.Combine(clipPaths.OutputsDir, "result.json");
        if (File.Exists(resultPath))
        {
            var json = File.ReadAllText(resultPath);
            var result = JsonSerializer.Deserialize<ResultRecord>(json);
            if (result != null && result.outputs?.overlay != null && result.status == "ok")
            {
                LoadOverlay(result.outputs.overlay);
            }
        }
        else
        {
            AppendLog("result.json not found.");
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

    private void LoadOverlay(string overlayPath)
    {
        if (!File.Exists(overlayPath))
        {
            AppendLog("Overlay video not found.");
            return;
        }

        PreviewPlayer.Stop();
        PreviewPlayer.Source = new Uri(overlayPath);
        PreviewPlayer.Play();
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
        var logsDir = _lastLogsDir ?? StoragePaths.LogsDir();
        Process.Start(new ProcessStartInfo("explorer.exe", logsDir) { UseShellExecute = true });
    }

    private void AppendLog(string message)
    {
        Dispatcher.Invoke(() =>
        {
            LogTextBox.AppendText(message + Environment.NewLine);
            LogTextBox.ScrollToEnd();
        });
        File.AppendAllText(_desktopLogPath, message + Environment.NewLine);
    }

    private record ProfileItem(string Id, string Name)
    {
        public override string ToString() => Name;
    }

    private record ProfileRecord(string id, string name, string created_at);

    private record ResultRecord(string status, OutputRecord? outputs);

    private record OutputRecord(string overlay, string pose);
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
}

public record EngineInfo(string EnginePath);
