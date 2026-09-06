import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Single point of truth for the one secret this app ever stores: the JWT.
/// Everything else (server URL, pipeline preferences) is plain user
/// preference and lives in `shared_preferences` via [SettingsController]
/// instead — see that file's docstring for why.
class SecureStorage {
  static const _tokenKey = 'auth_token';

  final FlutterSecureStorage _storage;

  SecureStorage({FlutterSecureStorage? storage}) : _storage = storage ?? const FlutterSecureStorage();

  Future<String?> readToken() => _storage.read(key: _tokenKey);

  Future<void> writeToken(String token) => _storage.write(key: _tokenKey, value: token);

  Future<void> deleteToken() => _storage.delete(key: _tokenKey);
}
