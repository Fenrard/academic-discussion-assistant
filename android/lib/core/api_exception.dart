/// Thrown by [ApiClient] for any non-2xx HTTP response. Carries the parsed
/// FastAPI `{"detail": "..."}` message when one is present (every backend
/// route uses plain `HTTPException(detail=...)` — no custom error envelope
/// anywhere in `backend/api/`), otherwise a generic fallback.
class ApiException implements Exception {
  final int? statusCode;
  final String message;

  const ApiException(this.statusCode, this.message);

  bool get isUnauthorized => statusCode == 401;
  bool get isRateLimited => statusCode == 429;
  bool get isConflict => statusCode == 409;

  @override
  String toString() => 'ApiException($statusCode, $message)';
}
