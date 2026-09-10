import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:scaitale_client/core/api_client.dart';
import 'package:scaitale_client/core/api_exception.dart';

ApiClient _client(MockClient mock) => ApiClient(getBaseUrl: () => 'http://x', httpClient: mock);

void main() {
  group('ApiClient response handling', () {
    test('exportMinutes returns the raw (non-JSON) body on success', () async {
      // Regression: exportMinutes used to route through _handle(), whose 2xx
      // branch runs jsonDecode() on the body — so every *successful* export of
      // the markdown/plain-text minutes threw a FormatException and the
      // "Share minutes" action silently did nothing.
      const markdown = '# Minutes: Lecture 1\nGenerated: 2026-09-11\n- point';
      final client = _client(MockClient((req) async {
        expect(req.url.queryParameters['format'], 'markdown');
        return http.Response(markdown, 200, headers: {'content-type': 'text/plain; charset=utf-8'});
      }));

      final body = await client.exportMinutes('sess-1');
      expect(body, markdown);
    });

    test('exportMinutes surfaces a non-2xx as an ApiException with the server detail', () async {
      final client = _client(MockClient((req) async =>
          http.Response('{"detail":"Minutes have not been generated yet for this session."}', 409)));

      expect(
        () => client.exportMinutes('sess-1'),
        throwsA(isA<ApiException>()
            .having((e) => e.statusCode, 'statusCode', 409)
            .having((e) => e.message, 'message', contains('not been generated'))),
      );
    });

    test('a 401 on any call fires onUnauthorized exactly once and still throws', () async {
      var unauthorizedCalls = 0;
      final client = _client(MockClient((req) async => http.Response('{"detail":"Not authenticated"}', 401)))
        ..onUnauthorized = (() => unauthorizedCalls++);

      await expectLater(() => client.listSessions(), throwsA(isA<ApiException>()));
      expect(unauthorizedCalls, 1);
    });

    test('listSessions decodes a JSON array body', () async {
      final client = _client(MockClient((req) async => http.Response(
            '[{"id":"s1","title":null,"status":"completed","created_at":"2026-09-11T00:00:00Z","duration_seconds":12.0}]',
            200,
            headers: {'content-type': 'application/json'},
          )));
      final sessions = await client.listSessions();
      expect(sessions, hasLength(1));
      expect(sessions.first.id, 's1');
    });
  });
}
