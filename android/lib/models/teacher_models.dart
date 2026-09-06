/// Mirrors backend/schemas/teacher.py's TeacherOut.
class TeacherOut {
  final String id;
  final String name;
  final String status; // pending | ready | failed
  final String? errorDetail;
  final DateTime createdAt;

  const TeacherOut({
    required this.id,
    required this.name,
    required this.status,
    required this.errorDetail,
    required this.createdAt,
  });

  factory TeacherOut.fromJson(Map<String, dynamic> json) => TeacherOut(
        id: json['id'] as String,
        name: json['name'] as String,
        status: json['status'] as String,
        errorDetail: json['error_detail'] as String?,
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  bool get isPending => status == 'pending';
  bool get isReady => status == 'ready';
  bool get isFailed => status == 'failed';
}
