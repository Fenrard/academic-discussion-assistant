import 'session_models.dart';

/// The two client-to-server control frames on `/ws/transcribe`
/// (backend/api/transcribe.py). Binary audio frames are sent separately, not
/// modeled here — see WsTranscribeClient.sendChunk().
class StartFrame {
  final String? title;
  final bool consentConfirmed;
  final Map<String, dynamic> options;

  const StartFrame({required this.title, required this.consentConfirmed, required this.options});

  Map<String, dynamic> toJson() => {
        'type': 'start',
        'title': title,
        'consent_confirmed': consentConfirmed,
        'options': options,
      };
}

class EndFrame {
  const EndFrame();
  Map<String, dynamic> toJson() => {'type': 'end'};
}

/// Server-to-client frames, dispatched by their `type` field. A sealed class
/// so every consumer's `switch` is exhaustive-checked by the analyzer.
sealed class WsServerMessage {
  const WsServerMessage();

  factory WsServerMessage.fromJson(Map<String, dynamic> json) {
    switch (json['type'] as String?) {
      case 'session_started':
        return SessionStartedMessage(sessionId: json['session_id'] as String);
      case 'chunk_result':
        return ChunkResultMessage(
          chunkIndex: json['chunk_index'] as int,
          text: json['text'] as String? ?? '',
          language: json['language'] as String?,
          whisperSegments: ((json['whisper_segments'] as List?) ?? const [])
              .map((e) => TranscriptSegment.fromJson(e as Map<String, dynamic>))
              .toList(),
          transcriptSoFar: json['transcript_so_far'] as String? ?? '',
        );
      case 'error':
        return WsErrorMessage(
          chunkIndex: json['chunk_index'] as int?,
          detail: json['detail'] as String? ?? 'Unknown error.',
        );
      case 'session_ended':
        return SessionEndedMessage(
          sessionId: json['session_id'] as String,
          transcript: json['transcript'] as String? ?? '',
          keywords: ((json['keywords'] as List?) ?? const []).map((e) => e as String).toList(),
          minutes: json['minutes'] as Map<String, dynamic>?,
        );
      default:
        return WsErrorMessage(chunkIndex: null, detail: 'Unrecognized message type: ${json['type']}');
    }
  }
}

class SessionStartedMessage extends WsServerMessage {
  final String sessionId;
  const SessionStartedMessage({required this.sessionId});
}

class ChunkResultMessage extends WsServerMessage {
  final int chunkIndex;
  final String text;
  final String? language;
  final List<TranscriptSegment> whisperSegments;
  final String transcriptSoFar;

  const ChunkResultMessage({
    required this.chunkIndex,
    required this.text,
    required this.language,
    required this.whisperSegments,
    required this.transcriptSoFar,
  });
}

class WsErrorMessage extends WsServerMessage {
  final int? chunkIndex;
  final String detail;
  const WsErrorMessage({required this.chunkIndex, required this.detail});
}

class SessionEndedMessage extends WsServerMessage {
  final String sessionId;
  final String transcript;
  final List<String> keywords;
  final Map<String, dynamic>? minutes;

  const SessionEndedMessage({
    required this.sessionId,
    required this.transcript,
    required this.keywords,
    required this.minutes,
  });
}
