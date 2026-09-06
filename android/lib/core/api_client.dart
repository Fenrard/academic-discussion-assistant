import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../models/auth_models.dart';
import '../models/session_models.dart';
import '../models/teacher_models.dart';
import 'api_exception.dart';

/// Thin REST wrapper — one method per backend/api/*.py endpoint. Reads the
/// base URL and current token via closures (not a cached value, not a
/// concrete AuthController/SettingsController reference) so a Settings
/// change takes effect on the very next call, and so this class has no
/// circular dependency on AuthController despite AuthController needing an
/// ApiClient to make its own login/register calls — AuthController calls
/// [setToken] directly on this instance after login/logout/restore instead
/// of ApiClient pulling the token from AuthController.
class ApiClient {
  final String Function() getBaseUrl;
  final http.Client _http;

  String? _token;

  /// Set by main.dart after both this client and AuthController exist:
  /// `apiClient.onUnauthorized = authController.forceLogout;`. Called once
  /// per request that comes back 401, so every screen gets the same
  /// "session expired, back to login" behavior with no per-screen handling.
  void Function()? onUnauthorized;

  ApiClient({required this.getBaseUrl, http.Client? httpClient}) : _http = httpClient ?? http.Client();

  void setToken(String? token) => _token = token;

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('${getBaseUrl()}/api/v1$path').replace(queryParameters: query);

  Map<String, String> get _authHeader => _token == null ? {} : {'Authorization': 'Bearer $_token'};

  // --- Auth ---

  Future<UserOut> register(String email, String password) async {
    final response = await _http.post(
      _uri('/auth/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    return UserOut.fromJson(_decodeMap(_handle(response)));
  }

  Future<TokenResponse> login(String email, String password) async {
    // OAuth2PasswordRequestForm's field is named "username" by spec; the
    // backend authenticates by email (backend/api/auth.py's own comment).
    final response = await _http.post(_uri('/auth/login'), body: {'username': email, 'password': password});
    return TokenResponse.fromJson(_decodeMap(_handle(response)));
  }

  // --- Sessions ---

  Future<List<SessionSummary>> listSessions() async {
    final response = await _http.get(_uri('/sessions'), headers: _authHeader);
    return _decodeList(_handle(response)).map((e) => SessionSummary.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<SessionDetail> getSession(String id) async {
    final response = await _http.get(_uri('/sessions/$id'), headers: _authHeader);
    return SessionDetail.fromJson(_decodeMap(_handle(response)));
  }

  Future<void> deleteSession(String id) async {
    final response = await _http.delete(_uri('/sessions/$id'), headers: _authHeader);
    _handle(response);
  }

  // --- Teachers ---

  Future<TeacherOut> enrollTeacher(String name, Uint8List audioBytes, {String filename = 'sample.wav'}) async {
    final request = http.MultipartRequest('POST', _uri('/teachers/enroll'))
      ..headers.addAll(_authHeader)
      ..fields['name'] = name
      ..files.add(http.MultipartFile.fromBytes('file', audioBytes, filename: filename));
    final streamed = await _http.send(request);
    final response = await http.Response.fromStream(streamed);
    return TeacherOut.fromJson(_decodeMap(_handle(response)));
  }

  Future<List<TeacherOut>> listTeachers() async {
    final response = await _http.get(_uri('/teachers'), headers: _authHeader);
    return _decodeList(_handle(response)).map((e) => TeacherOut.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<TeacherOut> getTeacher(String id) async {
    final response = await _http.get(_uri('/teachers/$id'), headers: _authHeader);
    return TeacherOut.fromJson(_decodeMap(_handle(response)));
  }

  Future<void> deleteTeacher(String id) async {
    final response = await _http.delete(_uri('/teachers/$id'), headers: _authHeader);
    _handle(response);
  }

  // --- Minutes ---

  Future<Map<String, dynamic>> getMinutes(String sessionId) async {
    final response = await _http.get(_uri('/sessions/$sessionId/minutes'), headers: _authHeader);
    return _decodeMap(_handle(response));
  }

  Future<String> exportMinutes(String sessionId, {String format = 'markdown'}) async {
    final response = await _http.get(_uri('/sessions/$sessionId/minutes/export', {'format': format}), headers: _authHeader);
    _handle(response);
    return response.body;
  }

  // --- Shared response handling ---

  /// Returns the decoded body on 2xx; throws [ApiException] otherwise and
  /// fires [onUnauthorized] on 401. The one place every call funnels through.
  dynamic _handle(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return response.body.isEmpty ? null : jsonDecode(response.body);
    }

    String message = 'Request failed (${response.statusCode}).';
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map && decoded['detail'] != null) {
        message = decoded['detail'].toString();
      }
    } catch (_) {
      // Non-JSON error body (e.g. a raw 5xx from an intermediary) — keep the generic message.
    }

    if (response.statusCode == 401) {
      onUnauthorized?.call();
    }
    throw ApiException(response.statusCode, message);
  }

  Map<String, dynamic> _decodeMap(dynamic decoded) => decoded as Map<String, dynamic>;
  List<dynamic> _decodeList(dynamic decoded) => decoded as List<dynamic>;
}
