import 'package:flutter_test/flutter_test.dart';
import 'package:scaitale_client/core/polling.dart';

void main() {
  group('pollUntil', () {
    test('returns immediately when the first fetch is already done', () async {
      var callCount = 0;
      final result = await pollUntil<int>(
        fetch: () async {
          callCount++;
          return 42;
        },
        isDone: (value) => value == 42,
        initial: const Duration(milliseconds: 1),
      );
      expect(result, 42);
      expect(callCount, 1);
    });

    test('keeps polling until isDone reports true', () async {
      var callCount = 0;
      final result = await pollUntil<String>(
        fetch: () async {
          callCount++;
          return callCount >= 3 ? 'ready' : 'pending';
        },
        isDone: (value) => value == 'ready',
        initial: const Duration(milliseconds: 1),
        maxInterval: const Duration(milliseconds: 2),
      );
      expect(result, 'ready');
      expect(callCount, 3);
    });

    test('throws PollTimeoutException when the deadline passes without success', () async {
      expect(
        () => pollUntil<String>(
          fetch: () async => 'pending',
          isDone: (value) => value == 'ready',
          initial: const Duration(milliseconds: 1),
          maxInterval: const Duration(milliseconds: 2),
          timeout: const Duration(milliseconds: 20),
        ),
        throwsA(isA<PollTimeoutException>()),
      );
    });

    test('propagates an exception thrown by fetch instead of swallowing it', () async {
      expect(
        () => pollUntil<int>(
          fetch: () async => throw StateError('network error'),
          isDone: (_) => true,
        ),
        throwsA(isA<StateError>()),
      );
    });
  });
}
