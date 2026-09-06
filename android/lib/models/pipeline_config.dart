/// Client-side pipeline presets (CLAUDE.md: "Presets defined client-side in
/// pipeline_config.dart... backend never sees preset names"). [Preset] never
/// appears in a serialized request — only [PipelineOptions.toJson()] does.
enum Preset { fast, balanced, accurate }

/// Mirrors `backend/schemas/pipeline.py`'s `PipelineOptions` field-for-field.
/// Field names in [toJson] must match that schema exactly — this is the
/// single highest-risk typo surface in the app, since a mismatched key is
/// silently ignored by Pydantic's defaults rather than raising an error.
class PipelineOptions {
  final bool enableDenoise;
  final bool enableVad;
  final bool enableDiarization;
  final bool enableTeacherVerification;
  final int? numSpeakers;
  final int beamSize;
  final double chunkDurationSeconds;

  const PipelineOptions({
    required this.enableDenoise,
    required this.enableVad,
    required this.enableDiarization,
    required this.enableTeacherVerification,
    required this.numSpeakers,
    required this.beamSize,
    required this.chunkDurationSeconds,
  });

  factory PipelineOptions.fromJson(Map<String, dynamic> json) => PipelineOptions(
        enableDenoise: json['enable_denoise'] as bool? ?? false,
        enableVad: json['enable_vad'] as bool? ?? true,
        enableDiarization: json['enable_diarization'] as bool? ?? false,
        enableTeacherVerification: json['enable_teacher_verification'] as bool? ?? false,
        numSpeakers: json['num_speakers'] as int?,
        beamSize: json['beam_size'] as int? ?? 5,
        chunkDurationSeconds: (json['chunk_duration_seconds'] as num?)?.toDouble() ?? 3.0,
      );

  Map<String, dynamic> toJson() => {
        'enable_denoise': enableDenoise,
        'enable_vad': enableVad,
        'enable_diarization': enableDiarization,
        'enable_teacher_verification': enableTeacherVerification,
        'num_speakers': numSpeakers,
        'beam_size': beamSize,
        'chunk_duration_seconds': chunkDurationSeconds,
      };

  PipelineOptions copyWith({
    bool? enableDenoise,
    bool? enableVad,
    bool? enableDiarization,
    bool? enableTeacherVerification,
    int? Function()? numSpeakers,
    int? beamSize,
    double? chunkDurationSeconds,
  }) {
    return PipelineOptions(
      enableDenoise: enableDenoise ?? this.enableDenoise,
      enableVad: enableVad ?? this.enableVad,
      enableDiarization: enableDiarization ?? this.enableDiarization,
      enableTeacherVerification: enableTeacherVerification ?? this.enableTeacherVerification,
      numSpeakers: numSpeakers != null ? numSpeakers() : this.numSpeakers,
      beamSize: beamSize ?? this.beamSize,
      chunkDurationSeconds: chunkDurationSeconds ?? this.chunkDurationSeconds,
    );
  }

  @override
  bool operator ==(Object other) =>
      other is PipelineOptions &&
      other.enableDenoise == enableDenoise &&
      other.enableVad == enableVad &&
      other.enableDiarization == enableDiarization &&
      other.enableTeacherVerification == enableTeacherVerification &&
      other.numSpeakers == numSpeakers &&
      other.beamSize == beamSize &&
      other.chunkDurationSeconds == chunkDurationSeconds;

  @override
  int get hashCode => Object.hash(
        enableDenoise,
        enableVad,
        enableDiarization,
        enableTeacherVerification,
        numSpeakers,
        beamSize,
        chunkDurationSeconds,
      );
}

/// Beam size range exposed on the "accuracy vs. speed" slider. The backend
/// schema has no upper bound; 1-10 is Faster-Whisper's practical range on a
/// CPU int8 model — going higher just burns CPU with no real accuracy gain
/// on this model size.
const kMinBeamSize = 1;
const kMaxBeamSize = 10;

/// Matches backend/core/config.py's min/max_chunk_duration_seconds exactly —
/// duplicated here deliberately (client and server are separate deployables
/// with no shared source), not a drift risk since both sides are effectively
/// locked constants from the same spec.
const kMinChunkDurationSeconds = 1.0;
const kMaxChunkDurationSeconds = 10.0;

class PipelinePresets {
  static const fast = PipelineOptions(
    enableDenoise: false,
    enableVad: true,
    enableDiarization: false,
    enableTeacherVerification: false,
    numSpeakers: null,
    beamSize: 1,
    chunkDurationSeconds: 2.0,
  );

  // Matches backend/schemas/pipeline.py's own field defaults exactly.
  static const balanced = PipelineOptions(
    enableDenoise: false,
    enableVad: true,
    enableDiarization: false,
    enableTeacherVerification: false,
    numSpeakers: null,
    beamSize: 5,
    chunkDurationSeconds: 3.0,
  );

  static const accurate = PipelineOptions(
    enableDenoise: true,
    enableVad: true,
    enableDiarization: true,
    enableTeacherVerification: true,
    numSpeakers: null,
    beamSize: 8,
    chunkDurationSeconds: 5.0,
  );

  static PipelineOptions resolve(Preset preset) => switch (preset) {
        Preset.fast => fast,
        Preset.balanced => balanced,
        Preset.accurate => accurate,
      };

  /// Returns the matching preset for a given set of options, or null if it
  /// doesn't exactly match any of the three (i.e. the user has customized it
  /// via the advanced panel) — used to decide whether the UI shows "Fast" /
  /// "Balanced" / "Accurate" or "Custom".
  static Preset? matching(PipelineOptions options) {
    if (options == fast) return Preset.fast;
    if (options == balanced) return Preset.balanced;
    if (options == accurate) return Preset.accurate;
    return null;
  }
}

extension PresetLabel on Preset {
  String get label => switch (this) {
        Preset.fast => 'Fast',
        Preset.balanced => 'Balanced',
        Preset.accurate => 'Accurate',
      };
}
