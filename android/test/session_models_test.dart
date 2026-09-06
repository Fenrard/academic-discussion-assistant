import 'package:flutter_test/flutter_test.dart';
import 'package:scaitale_client/models/session_models.dart';

void main() {
  group('SessionSummary.fromJson', () {
    test('parses a complete summary', () {
      final summary = SessionSummary.fromJson({
        'id': 's1',
        'title': 'Algebra intro',
        'status': 'completed',
        'created_at': '2026-09-01T10:00:00Z',
        'duration_seconds': 120.5,
      });
      expect(summary.id, 's1');
      expect(summary.title, 'Algebra intro');
      expect(summary.status, 'completed');
      expect(summary.durationSeconds, 120.5);
      expect(summary.isProcessing, isFalse);
    });

    test('handles a null title and duration', () {
      final summary = SessionSummary.fromJson({
        'id': 's2',
        'title': null,
        'status': 'processing',
        'created_at': '2026-09-01T10:00:00Z',
        'duration_seconds': null,
      });
      expect(summary.title, isNull);
      expect(summary.durationSeconds, isNull);
      expect(summary.isProcessing, isTrue);
    });

    test('isProcessing recognizes both processing and in_progress', () {
      final base = {'id': 's3', 'title': null, 'created_at': '2026-09-01T10:00:00Z', 'duration_seconds': null};
      expect(SessionSummary.fromJson({...base, 'status': 'in_progress'}).isProcessing, isTrue);
      expect(SessionSummary.fromJson({...base, 'status': 'interrupted'}).isProcessing, isFalse);
    });
  });

  group('TranscriptSegment.fromJson', () {
    test('parses a segment with no diarization/teacher-verification data', () {
      final segment = TranscriptSegment.fromJson({
        'start': 0.0,
        'end': 2.5,
        'text': 'Magandang umaga',
        'avg_logprob': -0.2,
        'no_speech_prob': 0.01,
      });
      expect(segment.text, 'Magandang umaga');
      expect(segment.speaker, isNull);
      expect(segment.isTeacher, isNull);
      expect(segment.teacherName, isNull);
      expect(segment.confidence, isNull);
    });

    test('parses a segment with diarization and teacher-verification data present', () {
      final segment = TranscriptSegment.fromJson({
        'start': 2.5,
        'end': 5.0,
        'text': 'Buksan ang inyong libro',
        'speaker': 'Speaker A',
        'is_teacher': true,
        'teacher_name': 'Mrs. Santos',
        'confidence': 0.87,
      });
      expect(segment.speaker, 'Speaker A');
      expect(segment.isTeacher, isTrue);
      expect(segment.teacherName, 'Mrs. Santos');
      expect(segment.confidence, 0.87);
    });
  });

  group('SessionDetail.fromJson', () {
    test('parses a full detail payload including nested segments', () {
      final detail = SessionDetail.fromJson({
        'id': 's1',
        'title': 'Lecture 1',
        'status': 'completed',
        'created_at': '2026-09-01T10:00:00Z',
        'duration_seconds': 300.0,
        'consent_confirmed': true,
        'pipeline_options': {'enable_vad': true},
        'transcript_text': 'Hello class',
        'transcript_segments': [
          {'start': 0.0, 'end': 1.0, 'text': 'Hello class'},
        ],
        'speaker_segments': [],
        'keywords': ['algebra', 'equation'],
        'minutes': {'generated_at': '2026-09-01T10:05:00Z'},
        'stage_latencies': {'transcribe': 1.2},
      });

      expect(detail.transcriptSegments, hasLength(1));
      expect(detail.transcriptSegments.first.text, 'Hello class');
      expect(detail.keywords, ['algebra', 'equation']);
      expect(detail.minutes, isNotNull);
      expect(detail.isProcessing, isFalse);
    });

    test('defaults every optional/newer field when absent, without throwing', () {
      final detail = SessionDetail.fromJson({
        'id': 's2',
        'title': null,
        'status': 'processing',
        'created_at': '2026-09-01T10:00:00Z',
        'duration_seconds': null,
      });

      expect(detail.consentConfirmed, isFalse);
      expect(detail.pipelineOptions, isEmpty);
      expect(detail.transcriptText, isEmpty);
      expect(detail.transcriptSegments, isEmpty);
      expect(detail.speakerSegments, isEmpty);
      expect(detail.keywords, isEmpty);
      expect(detail.minutes, isNull);
      expect(detail.stageLatencies, isEmpty);
      expect(detail.isProcessing, isTrue);
    });
  });
}
