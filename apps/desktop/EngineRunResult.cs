using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace FightingOverlay.Desktop;

public class EngineRunResult
{
    [JsonPropertyName("status")]
    public string? Status { get; set; }

    [JsonPropertyName("error")]
    public EngineRunError? Error { get; set; }

    [JsonPropertyName("outputs")]
    public EngineRunOutputs? Outputs { get; set; }

    [JsonPropertyName("logs")]
    public EngineRunLogs? Logs { get; set; }

    [JsonPropertyName("inputs")]
    public EngineRunInputs? Inputs { get; set; }

    [JsonPropertyName("version")]
    public string? Version { get; set; }

    [JsonPropertyName("run_id")]
    public string? RunId { get; set; }

    [JsonPropertyName("started_at")]
    public string? StartedAt { get; set; }

    [JsonPropertyName("finished_at")]
    public string? FinishedAt { get; set; }

    [JsonPropertyName("warnings")]
    public List<string>? Warnings { get; set; }

    [JsonPropertyName("assigned_profiles")]
    public List<AssignedProfile>? AssignedProfiles { get; set; }

    [JsonPropertyName("stdout")]
    public string? Stdout { get; set; }

    [JsonPropertyName("stderr")]
    public string? Stderr { get; set; }

    public static EngineRunResult LoadFromFile(string path)
    {
        var json = File.ReadAllText(path);
        return FromJson(json);
    }

    public static EngineRunResult FromJson(string json)
    {
        var options = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };
        return JsonSerializer.Deserialize<EngineRunResult>(json, options) ?? new EngineRunResult();
    }

    public string ToJson()
    {
        var options = new JsonSerializerOptions
        {
            WriteIndented = true
        };
        return JsonSerializer.Serialize(this, options);
    }

    public string? ResolveOverlayPath(string outputsDir)
    {
        var overlay = Outputs?.OverlayMp4;
        if (string.IsNullOrWhiteSpace(overlay))
        {
            return null;
        }

        if (Path.IsPathRooted(overlay))
        {
            return overlay;
        }

        return Path.Combine(outputsDir, overlay);
    }
}

public class AssignedProfile
{
    [JsonPropertyName("track_id")]
    public string? TrackId { get; set; }

    [JsonPropertyName("profile_id")]
    public string? ProfileId { get; set; }
}

public class EngineRunError
{
    [JsonPropertyName("code")]
    public string? Code { get; set; }

    [JsonPropertyName("message")]
    public string? Message { get; set; }

    [JsonPropertyName("hint")]
    public string? Hint { get; set; }

    [JsonPropertyName("details")]
    public Dictionary<string, object?>? Details { get; set; }
}

public class EngineRunOutputs
{
    [JsonPropertyName("overlay_mp4")]
    public string? OverlayMp4 { get; set; }

    [JsonPropertyName("pose_json")]
    public string? PoseJson { get; set; }

    [JsonPropertyName("result_json")]
    public string? ResultJson { get; set; }

    [JsonPropertyName("error_json")]
    public string? ErrorJson { get; set; }

    [JsonPropertyName("outputs_dir")]
    public string? OutputsDir { get; set; }
}

public class EngineRunLogs
{
    [JsonPropertyName("engine_log")]
    public string? EngineLog { get; set; }

    [JsonPropertyName("logs_dir")]
    public string? LogsDir { get; set; }

    [JsonPropertyName("desktop_log")]
    public string? DesktopLog { get; set; }
}

public class EngineRunInputs
{
    [JsonPropertyName("video")]
    public string? Video { get; set; }

    [JsonPropertyName("run_id")]
    public string? RunId { get; set; }
}
