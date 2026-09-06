/// Shared exponential-backoff poll loop, used identically for whole-file
/// transcription's session-status polling and teacher-enrollment status
/// polling (both are 202-accepted-then-poll patterns on the backend).
///
/// Backoff: 1s, 2s, 4s, 8s, 8s, 8s... capped at [maxInterval], gives up past
/// [timeout] with a [PollTimeoutException].
Future<T> pollUntil<T>({
  required Future<T> Function() fetch,
  required bool Function(T value) isDone,
  Duration initial = const Duration(seconds: 1),
  Duration maxInterval = const Duration(seconds: 8),
  Duration timeout = const Duration(minutes: 5),
}) async {
  final deadline = DateTime.now().add(timeout);
  var interval = initial;

  while (true) {
    final value = await fetch();
    if (isDone(value)) return value;

    if (DateTime.now().isAfter(deadline)) {
      throw PollTimeoutException('Timed out after ${timeout.inSeconds}s waiting for a result.');
    }

    await Future<void>.delayed(interval);
    final doubled = interval * 2;
    interval = doubled > maxInterval ? maxInterval : doubled;
  }
}

class PollTimeoutException implements Exception {
  final String message;
  const PollTimeoutException(this.message);

  @override
  String toString() => 'PollTimeoutException: $message';
}
