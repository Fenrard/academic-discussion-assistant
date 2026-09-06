import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/auth_controller.dart';
import 'screens/auth/login_screen.dart';
import 'screens/home/home_screen.dart';

/// Root widget: theme + auth-gated initial route. Listens to AuthController
/// so a forced logout (401 from anywhere) or a normal logout immediately
/// swaps the whole navigator stack back to LoginScreen — the single 401
/// handling path for the app, not per-screen logic.
class ScaitaleApp extends StatelessWidget {
  const ScaitaleApp({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();

    return MaterialApp(
      title: 'Scaitale',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true, brightness: Brightness.light),
      darkTheme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true, brightness: Brightness.dark),
      home: auth.isAuthenticated ? const HomeScreen() : const LoginScreen(),
    );
  }
}
