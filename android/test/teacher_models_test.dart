import 'package:flutter_test/flutter_test.dart';
import 'package:scaitale_client/models/teacher_models.dart';

void main() {
  group('TeacherOut.fromJson', () {
    test('parses a ready teacher with no error detail', () {
      final teacher = TeacherOut.fromJson({
        'id': 't1',
        'name': 'Mrs. Santos',
        'status': 'ready',
        'error_detail': null,
        'created_at': '2026-09-01T10:00:00Z',
      });
      expect(teacher.isReady, isTrue);
      expect(teacher.isPending, isFalse);
      expect(teacher.isFailed, isFalse);
      expect(teacher.errorDetail, isNull);
    });

    test('parses a failed teacher with an error detail', () {
      final teacher = TeacherOut.fromJson({
        'id': 't2',
        'name': 'Mr. Cruz',
        'status': 'failed',
        'error_detail': 'Sample too short to extract an embedding.',
        'created_at': '2026-09-01T10:00:00Z',
      });
      expect(teacher.isFailed, isTrue);
      expect(teacher.errorDetail, 'Sample too short to extract an embedding.');
    });

    test('parses a pending teacher', () {
      final teacher = TeacherOut.fromJson({
        'id': 't3',
        'name': 'Ms. Reyes',
        'status': 'pending',
        'error_detail': null,
        'created_at': '2026-09-01T10:00:00Z',
      });
      expect(teacher.isPending, isTrue);
    });
  });
}
