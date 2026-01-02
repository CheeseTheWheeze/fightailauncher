using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace FightingOverlay.Desktop;

public class EngineRunner
{
    private const int PollDelayMs = 200;
    private static readonly TimeSpan ResultGracePeriod = TimeSpan.FromSeconds(2);
    private readonly EngineInfo _engineInfo;

    public EngineRunner(EngineInfo engineInfo)
    {
        _engineInfo = engineInfo;
    }

    public async Task<EngineRunResult> RunAnalyzeAsync(string videoPath, string athleteId, string clipId, Action<string> appendLog)
    {
        var clipPaths = StoragePaths.GetClipPaths(athleteId, clipId);
        Directory.CreateDirectory(clipPaths.InputDir);
        Directory.CreateDirectory(clipPaths.OutputsDir);
        Directory.CreateDirectory(clipPaths.LogsDir);

        var outputsDir = clipPaths.OutputsDir;
        var logsDir = clipPaths.LogsDir;
        var resultPath = Path.Combine(outputsDir, "result.json");
        var stdout = new StringBuilder();
        var stderr = new StringBuilder();

        var startInfo = new ProcessStartInfo
        {
            FileName = _engineInfo.EnginePath,
            Arguments = BuildArgs(videoPath, athleteId, clipId, outputsDir),
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
                appendLog(eventArgs.Data);
                AppendLine(stdout, eventArgs.Data);
            }
        };
        process.ErrorDataReceived += (_, eventArgs) =>
        {
            if (eventArgs.Data != null)
            {
                appendLog($"ERR: {eventArgs.Data}");
                AppendLine(stderr, eventArgs.Data);
            }
        };

        try
        {
            process.Start();
        }
        catch (Exception ex)
        {
            Logger.Log($"Engine failed to start: {ex}");
            return WriteFallbackResult(
                resultPath,
                outputsDir,
                logsDir,
                "E_ENGINE_START",
                "Engine failed to start.",
                "Verify the engine executable path and permissions.",
                stdout.ToString(),
                stderr.ToString());
        }

        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        while (!process.HasExited && !File.Exists(resultPath))
        {
            await Task.Delay(PollDelayMs);
        }

        if (!process.HasExited)
        {
            await process.WaitForExitAsync();
        }

        var graceStart = Stopwatch.StartNew();
        while (!File.Exists(resultPath) && graceStart.Elapsed < ResultGracePeriod)
        {
            await Task.Delay(PollDelayMs);
        }

        if (File.Exists(resultPath))
        {
            try
            {
                return EngineRunResult.LoadFromFile(resultPath);
            }
            catch (Exception ex)
            {
                Logger.Log($"Failed to parse result.json: {ex}");
                return WriteFallbackResult(
                    resultPath,
                    outputsDir,
                    logsDir,
                    "E_BAD_RESULT",
                    "Engine produced an unreadable result.json.",
                    "Open Logs for details.",
                    stdout.ToString(),
                    stderr.ToString());
            }
        }

        return WriteFallbackResult(
            resultPath,
            outputsDir,
            logsDir,
            "E_NO_RESULT",
            "Engine exited without producing result.json.",
            "Open Logs and verify the engine output folder.",
            stdout.ToString(),
            stderr.ToString());
    }

    private static string BuildArgs(string videoPath, string athleteId, string clipId, string outputsDir)
    {
        return $"analyze --video \"{videoPath}\" --athlete {athleteId} --clip {clipId} --outdir \"{outputsDir}\"";
    }

    private static void AppendLine(StringBuilder builder, string line)
    {
        if (builder.Length > 0)
        {
            builder.AppendLine();
        }
        builder.Append(line);
    }

    private static EngineRunResult WriteFallbackResult(
        string resultPath,
        string outputsDir,
        string logsDir,
        string code,
        string message,
        string hint,
        string stdout,
        string stderr)
    {
        var payload = new EngineRunResult
        {
            Status = "error",
            Error = new EngineRunError
            {
                Code = code,
                Message = message,
                Hint = hint,
                Details = new System.Collections.Generic.Dictionary<string, object?>
                {
                    ["stdout"] = Truncate(stdout),
                    ["stderr"] = Truncate(stderr)
                }
            },
            Outputs = new EngineRunOutputs
            {
                OverlayMp4 = "overlay.mp4",
                PoseJson = "pose.json",
                ResultJson = "result.json",
                ErrorJson = "error.json",
                OutputsDir = outputsDir
            },
            Logs = new EngineRunLogs
            {
                EngineLog = "engine.log",
                LogsDir = logsDir,
                DesktopLog = Logger.LogFile
            }
        };

        Directory.CreateDirectory(outputsDir);
        var options = new JsonSerializerOptions { WriteIndented = true };
        File.WriteAllText(resultPath, JsonSerializer.Serialize(payload, options));
        var errorPath = Path.Combine(outputsDir, "error.json");
        File.WriteAllText(errorPath, JsonSerializer.Serialize(payload.Error, options));
        return payload;
    }

    private static string Truncate(string value, int maxLength = 4000)
    {
        if (string.IsNullOrEmpty(value))
        {
            return value;
        }

        if (value.Length <= maxLength)
        {
            return value;
        }

        return value[..maxLength] + "...(truncated)";
    }
}
