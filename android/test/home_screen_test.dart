import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:scaitale_client/core/api_client.dart';
import 'package:scaitale_client/screens/home/home_screen.dart';

void main() {
  testWidgets(
    'a failed swipe-delete does not crash the list on the next reload',
    (tester) async {
      // Regression test: SessionListTile's Dismissible calls onDismissed
      // exactly once after animating itself out of the tree. HomeScreen's
      // old _delete() only removed the session from `_sessions` on a
      // *successful* server delete -- so after a failed delete, the item
      // stayed in the list, and the next rebuild (pull-to-refresh, or
      // returning from a new recording, both of which call _load()) recreated
      // a Dismissible with the same key on the already-"dismissed" State,
      // which Flutter refuses: "A dismissed Dismissible widget is still part
      // of the tree." Fixed by removing the item unconditionally in
      // _delete(), before the server call even resolves.
      // Two sessions, not one: after the failed delete below, the list must
      // stay non-empty so RefreshIndicator (not the empty-state view, which
      // has no pull-to-refresh) is what's on screen to trigger the reload.
      const sessionsJson = '['
          '{"id":"s1","title":"Lecture 1","status":"completed","created_at":"2026-09-11T00:00:00Z","duration_seconds":12.0},'
          '{"id":"s2","title":"Lecture 2","status":"completed","created_at":"2026-09-11T00:00:00Z","duration_seconds":8.0}'
          ']';
      var deleteCalls = 0;
      final apiClient = ApiClient(
        getBaseUrl: () => 'http://x',
        httpClient: MockClient((request) async {
          if (request.method == 'GET' && request.url.path.endsWith('/sessions')) {
            return http.Response(sessionsJson, 200); // the delete below never actually removes s1 server-side
          }
          if (request.method == 'DELETE') {
            deleteCalls++;
            return http.Response('{"detail":"server error"}', 500); // the delete FAILS server-side
          }
          return http.Response('{"detail":"not found"}', 404);
        }),
      );

      await tester.pumpWidget(
        Provider<ApiClient>.value(value: apiClient, child: const MaterialApp(home: HomeScreen())),
      );
      await tester.pumpAndSettle();
      expect(find.text('Lecture 1'), findsOneWidget);

      // Swipe the tile away (right-to-left, matching DismissDirection.endToStart).
      await tester.drag(find.text('Lecture 1'), const Offset(-500, 0));
      await tester.pumpAndSettle();

      expect(find.text('Delete session?'), findsOneWidget);
      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle(); // lets the failing DELETE call and its snackbar resolve
      expect(deleteCalls, 1);
      expect(find.text('Could not delete session: server error'), findsOneWidget);
      expect(find.text('Lecture 1'), findsNothing); // removed optimistically despite the failure

      // Simulate a pull-to-refresh (or returning from a new recording): this
      // is exactly the rebuild that used to crash. The session legitimately
      // reappears because the delete never actually succeeded server-side --
      // that's correct, self-healing behavior; the point is it doesn't crash.
      await tester.fling(find.byType(RefreshIndicator), const Offset(0, 300), 1000);
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Lecture 1'), findsOneWidget);
    },
  );
}
