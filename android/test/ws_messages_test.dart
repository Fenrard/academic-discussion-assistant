import 'package:flutter_test/flutter_test.dart';
import 'package:scaitale_client/models/ws_messages.dart';

void main() {
  group('StartFrame.toJson', () {
    test('produces the exact control-frame shape the backend expects', () {
      final frame = StartFrame(title: 'Lecture 1', consentConfirmed: true, options: {'enable_vad': true});
      expect(frame.toJson(), {
        'type': 'start',
        'title': 'Lecture 1',
        'consent_confirmed': true,
        'options': {'enable_vad': true},
      });
    });

    test('allows a null title', () {
      final frame = StartFrame(title: null, consentConfirmed: false, options: const {});
      expect(frame.toJson()['title'], isNull);
    });
  });

  test('EndFrame.toJson matches the backend contract', () {
    expect(const EndFrame().toJson(), {'type': 'end'});
  });

  group('WsServerMessage.fromJson', () {
    test('parses session_started', () {
      final message = WsServerMessage.fromJson({'type': 'session_started', 'session_id': 'abc123'});
      expect(message, isA<SessionStartedMessage>());
      expect((message as SessionStartedMessage).sessionId, 'abc123');
    });

    test('parses chunk_result with segments and transcript_so_far', () {
      final message = WsServerMessage.fromJson({
        'type': 'chunk_result',
        'chunk_index': 2,
        'text': 'Buksan ang libro',
        'language': 'tl',
        'whisper_segments': [
          {'start': 0.0, 'end': 1.5, 'text': 'Buksan ang libro'},
        ],
        'speaker_segments': [],
        'transcript_so_far': 'Magandang umaga. Buksan ang libro',
      });
      expect(message, isA<ChunkResultMessage>());
      final chunkResult = message as ChunkResultMessage;
      expect(chunkResult.chunkIndex, 2);
      expect(chunkResult.whisperSegments, hasLength(1));
      expect(chunkResult.transcriptSoFar, 'Magandang umaga. Buksan ang libro');
    });

    test('parses an error frame with a chunk index', () {
      final message = WsServerMessage.fromJson({'type': 'error', 'chunk_index': 1, 'detail': 'Model timed out.'});
      expect(message, isA<WsErrorMessage>());
      final error = message as WsErrorMessage;
      expect(error.chunkIndex, 1);
      expect(error.detail, 'Model timed out.');
    });

    test('parses a start-message error frame with no chunk index', () {
      final message = WsServerMessage.fromJson({'type': 'error', 'detail': 'First message must be start.'});
      expect((message as WsErrorMessage).chunkIndex, isNull);
    });

    test('parses session_ended with keywords and minutes', () {
      final message = WsServerMessage.fromJson({
        'type': 'session_ended',
        'session_id': 'abc123',
        'transcript': 'Full transcript text',
        'keywords': ['algebra'],
        'minutes': {'generated_at': '2026-09-01T10:05:00Z'},
      });
      expect(message, isA<SessionEndedMessage>());
      final ended = message as SessionEndedMessage;
      expect(ended.sessionId, 'abc123');
      expect(ended.keywords, ['algebra']);
      expect(ended.minutes, isNotNull);
    });

    test('falls back to an error message for an unrecognized type', () {
      final message = WsServerMessage.fromJson({'type': 'something_new'});
      expect(message, isA<WsErrorMessage>());
    });
  });
}
