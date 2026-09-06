import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'core/api_client.dart';
import 'core/auth_controller.dart';
import 'core/secure_storage.dart';
import 'core/settings_controller.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final settingsController = SettingsController();
  await settingsController.load();

  // ApiClient reads the base URL via a closure (not a cached value) so a
  // Settings change takes effect on the very next call.
  final apiClient = ApiClient(getBaseUrl: () => settingsController.baseUrl);

  final authController = AuthController(apiClient: apiClient, secureStorage: SecureStorage());
  // The single 401 handling path for the whole app: ApiClient calls this on
  // any 401 response, AuthController clears the token, ScaitaleApp's
  // auth-gated `home` swaps back to LoginScreen.
  apiClient.onUnauthorized = authController.forceLogout;
  await authController.tryRestoreSession();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<SettingsController>.value(value: settingsController),
        ChangeNotifierProvider<AuthController>.value(value: authController),
        Provider<ApiClient>.value(value: apiClient),
      ],
      child: const ScaitaleApp(),
    ),
  );
}
