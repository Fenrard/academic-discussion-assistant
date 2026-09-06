import 'package:flutter_test/flutter_test.dart';
import 'package:scaitale_client/models/minutes_models.dart';

void main() {
  group('Minutes.fromJson', () {
    test('parses a full minutes payload including the Round 4 fields', () {
      final minutes = Minutes.fromJson({
        'generated_at': '2026-09-01T10:05:00Z',
        'duration_seconds': 600.0,
        'participants': ['Teacher', 'Speaker A'],
        'teacher_speech_ratio': 0.62,
        'teacher_speakers': ['Speaker A'],
        'keywords': ['algebra', 'equation'],
        'topics': [
          {
            'label': 'Introduction',
            'start': 0.0,
            'end': 30.0,
            'key_points': ['Roll call', 'Today\'s agenda'],
          },
        ],
        'definitions': [
          {'term': 'Variable', 'definition': 'A symbol representing an unknown value.'},
        ],
        'action_items': [
          {'start': 45.0, 'speaker': 'Speaker A', 'text': 'Finish worksheet 3 by Friday.'},
        ],
      });

      expect(minutes.participants, ['Teacher', 'Speaker A']);
      expect(minutes.teacherSpeechRatio, 0.62);
      expect(minutes.teacherSpeakers, ['Speaker A']);
      expect(minutes.topics, hasLength(1));
      expect(minutes.topics.first.keyPoints, hasLength(2));
      expect(minutes.definitions.single.term, 'Variable');
      expect(minutes.actionItems.single.text, 'Finish worksheet 3 by Friday.');
    });

    test('defaults the fields a session finalized before Round 4 would lack', () {
      final minutes = Minutes.fromJson({
        'generated_at': '2026-01-01T00:00:00Z',
        'duration_seconds': 300.0,
        'participants': ['Unknown'],
        'keywords': [],
        'topics': [],
        'action_items': [],
      });

      expect(minutes.teacherSpeechRatio, isNull);
      expect(minutes.teacherSpeakers, isEmpty);
      expect(minutes.definitions, isEmpty);
    });
  });
}
