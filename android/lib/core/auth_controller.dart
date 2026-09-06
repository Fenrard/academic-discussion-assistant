import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'api_exception.dart';
import 'secure_storage.dart';

/// Holds the JWT and drives login/register/logout. Deliberately restores a
/// stored token *optimistically* at startup — there's no `/auth/me` endpoint
/// in the backend contract to proactively validate it, so an expired or
/// tampered token is only caught reactively on the first real API call's 401
/// (see [forceLogout], wired as ApiClient.onUnauthorized in main.dart).
class AuthController extends ChangeNotifier {
  final ApiClient _apiClient;
  final SecureStorage _secureStorage;

  String? _token;
  bool isLoading = false;
  String? error;

  AuthController({required ApiClient apiClient, required SecureStorage secureStorage})
      : _apiClient = apiClient,
        _secureStorage = secureStorage;

  bool get isAuthenticated => _token != null;
  String? get token => _token;

  Future<void> tryRestoreSession() async {
    final stored = await _secureStorage.readToken();
    _token = stored;
    _apiClient.setToken(stored);
    notifyListeners();
  }

  Future<bool> login(String email, String password) async {
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      final result = await _apiClient.login(email, password);
      _token = result.accessToken;
      _apiClient.setToken(_token);
      await _secureStorage.writeToken(_token!);
      return true;
    } on ApiException catch (e) {
      error = _loginErrorMessage(e);
      return false;
    } catch (_) {
      error = "Can't reach the server. Check your connection and Settings.";
      return false;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> register(String email, String password) async {
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      await _apiClient.register(email, password);
      return true;
    } on ApiException catch (e) {
      error = e.isConflict ? 'An account with this email already exists.' : e.message;
      return false;
    } catch (_) {
      error = "Can't reach the server. Check your connection and Settings.";
      return false;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  String _loginErrorMessage(ApiException e) {
    if (e.isUnauthorized) return 'Incorrect email or password.';
    if (e.isRateLimited) return 'Too many attempts — please wait a moment and try again.';
    return e.message;
  }

  /// The single 401 handling path for the whole app — wired as
  /// `apiClient.onUnauthorized` in main.dart, called from ApiClient's
  /// response handler, never invoked directly by a screen.
  Future<void> forceLogout() async {
    _token = null;
    _apiClient.setToken(null);
    await _secureStorage.deleteToken();
    notifyListeners();
  }

  Future<void> logout() => forceLogout();
}
