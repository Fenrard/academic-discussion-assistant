import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:scaitale_client/app.dart';
import 'package:scaitale_client/core/api_client.dart';
import 'package:scaitale_client/core/auth_controller.dart';
import 'package:scaitale_client/core/secure_storage.dart';
import 'package:scaitale_client/screens/auth/login_screen.dart';
import 'package:scaitale_client/screens/home/home_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// In-memory SecureStorage double -- no platform channel needed in a widget test.
class _FakeSecureStorage implements SecureStorage {
  String? _token;
  @override
  Future<String?> readToken() async => _token;
  @override
  Future<void> writeToken(String token) async => _token = token;
  @override
  Future<void> deleteToken() async => _token = null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  SharedPreferences.setMockInitialValues({});

  /// Regression coverage for ScaitaleApp's auth gate: `MaterialApp(home:
  /// auth.isAuthenticated ? HomeScreen : LoginScreen)` rebuilds `home` on every
  /// AuthController.notifyListeners() call, but Flutter's Navigator only reads
  /// `home` to build the *initial* route -- whether a later rebuild with a
  /// different `home` actually swaps the visible screen (rather than leaving
  /// whatever's already in the Navigator's route stack) is exactly the kind of
  /// thing that's easy to get subtly wrong and only shows up by actually
  /// running it, not by reading the code.
  testWidgets('logging in swaps LoginScreen for HomeScreen without navigation', (tester) async {
    final apiClient = ApiClient(
      getBaseUrl: () => 'http://x',
      httpClient: MockClient((request) async {
        if (request.url.path.endsWith('/auth/login')) {
          return http.Response('{"access_token":"tok123","token_type":"bearer"}', 200);
        }
        if (request.url.path.endsWith('/sessions')) {
          return http.Response('[]', 200); // HomeScreen's initial listSessions() call
        }
        return http.Response('{"detail":"not found"}', 404);
      }),
    );
    final auth = AuthController(apiClient: apiClient, secureStorage: _FakeSecureStorage());
    apiClient.onUnauthorized = auth.forceLogout;

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<AuthController>.value(value: auth),
          Provider<ApiClient>.value(value: apiClient),
        ],
        child: const ScaitaleApp(),
      ),
    );

    expect(find.byType(LoginScreen), findsOneWidget);
    expect(find.byType(HomeScreen), findsNothing);

    final loggedIn = await auth.login('teacher@example.com', 'password123');
    expect(loggedIn, isTrue);
    await tester.pumpAndSettle();

    expect(find.byType(HomeScreen), findsOneWidget,
        reason: 'ScaitaleApp rebuilt with home: HomeScreen after login, but the Navigator did not show it');
    expect(find.byType(LoginScreen), findsNothing);
  });

  testWidgets('forceLogout (a 401 from anywhere) swaps back to LoginScreen', (tester) async {
    final apiClient = ApiClient(
      getBaseUrl: () => 'http://x',
      httpClient: MockClient((request) async => http.Response('[]', 200)),
    );
    final storage = _FakeSecureStorage();
    await storage.writeToken('already-logged-in-token');
    final auth = AuthController(apiClient: apiClient, secureStorage: storage);
    apiClient.onUnauthorized = auth.forceLogout;
    await auth.tryRestoreSession();

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<AuthController>.value(value: auth),
          Provider<ApiClient>.value(value: apiClient),
        ],
        child: const ScaitaleApp(),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(HomeScreen), findsOneWidget);

    await auth.forceLogout();
    await tester.pumpAndSettle();

    expect(find.byType(LoginScreen), findsOneWidget,
        reason: 'forceLogout() did not bring the user back to LoginScreen');
    expect(find.byType(HomeScreen), findsNothing);
  });
}
