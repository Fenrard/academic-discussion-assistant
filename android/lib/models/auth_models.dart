/// Mirrors backend/schemas/auth.py.
class UserOut {
  final String id;
  final String email;
  final DateTime createdAt;

  const UserOut({required this.id, required this.email, required this.createdAt});

  factory UserOut.fromJson(Map<String, dynamic> json) => UserOut(
        id: json['id'] as String,
        email: json['email'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
      );
}

class TokenResponse {
  final String accessToken;
  final String tokenType;

  const TokenResponse({required this.accessToken, required this.tokenType});

  factory TokenResponse.fromJson(Map<String, dynamic> json) => TokenResponse(
        accessToken: json['access_token'] as String,
        tokenType: json['token_type'] as String? ?? 'bearer',
      );
}
