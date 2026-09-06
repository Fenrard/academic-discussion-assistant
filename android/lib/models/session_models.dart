/// Mirrors backend/schemas/session.py's SessionSummary.
class SessionSummary {
  final String id;
  final String? title;
  final String status;
  final DateTime createdAt;
  final double? durationSeconds;

  const SessionSummary({
    required this.id,
    required this.title,
    required this.status,
    required this.createdAt,
    required this.durationSeconds,
  });

  factory SessionSummary.fromJson(Map<String, dynamic> json) => SessionSummary(
        id: json['id'] as String,
        title: json['title'] as String?,
        status: json['status'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
        durationSeconds: (json['duration_seconds'] as num?)?.toDouble(),
      );

  /// The two statuses that mean "still being processed" — used to decide
  /// whether the Transcript screen should start polling.
  bool get isProcessing => status == 'processing' || status == 'in_progress';
}

/// One entry of `transcript_segments` / `whisper_segments`. Optional fields
/// are only present when diarization / teacher-verification actually ran
/// (backend/api's own docs: "speaker: added by merge step, Unknown if no
/// diarization overlap"; is_teacher/teacher_name/confidence only exist when
/// enable_teacher_verification was on) — every read here is null-safe.
class TranscriptSegment {
  final double start;
  final double end;
  final String text;
  final double? avgLogprob;
  final double? noSpeechProb;
  final String? speaker;
  final bool? isTeacher;
  final String? teacherName;
  final double? confidence;

  const TranscriptSegment({
    required this.start,
    required this.end,
    required this.text,
    this.avgLogprob,
    this.noSpeechProb,
    this.speaker,
    this.isTeacher,
    this.teacherName,
    this.confidence,
  });

  factory TranscriptSegment.fromJson(Map<String, dynamic> json) => TranscriptSegment(
        start: (json['start'] as num).toDouble(),
        end: (json['end'] as num).toDouble(),
        text: json['text'] as String? ?? '',
        avgLogprob: (json['avg_logprob'] as num?)?.toDouble(),
        noSpeechProb: (json['no_speech_prob'] as num?)?.toDouble(),
        speaker: json['speaker'] as String?,
        isTeacher: json['is_teacher'] as bool?,
        teacherName: json['teacher_name'] as String?,
        confidence: (json['confidence'] as num?)?.toDouble(),
      );
}

/// Mirrors backend/schemas/session.py's SessionDetail (SessionSummary + the
/// full pipeline output).
class SessionDetail {
  final String id;
  final String? title;
  final String status;
  final DateTime createdAt;
  final double? durationSeconds;
  final bool consentConfirmed;
  final Map<String, dynamic> pipelineOptions;
  final String transcriptText;
  final List<TranscriptSegment> transcriptSegments;
  final List<Map<String, dynamic>> speakerSegments;
  final List<String> keywords;
  final Map<String, dynamic>? minutes;
  final Map<String, dynamic> stageLatencies;

  const SessionDetail({
    required this.id,
    required this.title,
    required this.status,
    required this.createdAt,
    required this.durationSeconds,
    required this.consentConfirmed,
    required this.pipelineOptions,
    required this.transcriptText,
    required this.transcriptSegments,
    required this.speakerSegments,
    required this.keywords,
    required this.minutes,
    required this.stageLatencies,
  });

  factory SessionDetail.fromJson(Map<String, dynamic> json) => SessionDetail(
        id: json['id'] as String,
        title: json['title'] as String?,
        status: json['status'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
        durationSeconds: (json['duration_seconds'] as num?)?.toDouble(),
        consentConfirmed: json['consent_confirmed'] as bool? ?? false,
        pipelineOptions: (json['pipeline_options'] as Map<String, dynamic>?) ?? const {},
        transcriptText: json['transcript_text'] as String? ?? '',
        transcriptSegments: ((json['transcript_segments'] as List?) ?? const [])
            .map((e) => TranscriptSegment.fromJson(e as Map<String, dynamic>))
            .toList(),
        speakerSegments: ((json['speaker_segments'] as List?) ?? const [])
            .map((e) => e as Map<String, dynamic>)
            .toList(),
        keywords: ((json['keywords'] as List?) ?? const []).map((e) => e as String).toList(),
        minutes: json['minutes'] as Map<String, dynamic>?,
        stageLatencies: (json['stage_latencies'] as Map<String, dynamic>?) ?? const {},
      );

  bool get isProcessing => status == 'processing' || status == 'in_progress';
}
