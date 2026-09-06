/// Mirrors the dict shape produced by backend/services/minutes_service.py
/// and consumed by backend/api/minutes.py's `_render_minutes()`. The three
/// newer fields (teacherSpeechRatio, teacherSpeakers, definitions) are
/// nullable/defaulted here the same way `_render_minutes()` treats them with
/// `.get()` server-side — sessions finalized before Round 4 (CLAUDE.md) won't
/// have them.
class Topic {
  final String label;
  final double start;
  final double end;
  final List<String> keyPoints;

  const Topic({required this.label, required this.start, required this.end, required this.keyPoints});

  factory Topic.fromJson(Map<String, dynamic> json) => Topic(
        label: json['label'] as String? ?? '',
        start: (json['start'] as num?)?.toDouble() ?? 0,
        end: (json['end'] as num?)?.toDouble() ?? 0,
        keyPoints: ((json['key_points'] as List?) ?? const []).map((e) => e as String).toList(),
      );
}

class Definition {
  final String term;
  final String definition;

  const Definition({required this.term, required this.definition});

  factory Definition.fromJson(Map<String, dynamic> json) => Definition(
        term: json['term'] as String? ?? '',
        definition: json['definition'] as String? ?? '',
      );
}

class ActionItem {
  final double start;
  final String speaker;
  final String text;

  const ActionItem({required this.start, required this.speaker, required this.text});

  factory ActionItem.fromJson(Map<String, dynamic> json) => ActionItem(
        start: (json['start'] as num?)?.toDouble() ?? 0,
        speaker: json['speaker'] as String? ?? 'Unknown',
        text: json['text'] as String? ?? '',
      );
}

class Minutes {
  final String generatedAt;
  final double durationSeconds;
  final List<String> participants;
  final double? teacherSpeechRatio;
  final List<String> teacherSpeakers;
  final List<String> keywords;
  final List<Topic> topics;
  final List<Definition> definitions;
  final List<ActionItem> actionItems;

  const Minutes({
    required this.generatedAt,
    required this.durationSeconds,
    required this.participants,
    required this.teacherSpeechRatio,
    required this.teacherSpeakers,
    required this.keywords,
    required this.topics,
    required this.definitions,
    required this.actionItems,
  });

  factory Minutes.fromJson(Map<String, dynamic> json) => Minutes(
        generatedAt: json['generated_at'] as String? ?? '',
        durationSeconds: (json['duration_seconds'] as num?)?.toDouble() ?? 0,
        participants: ((json['participants'] as List?) ?? const []).map((e) => e as String).toList(),
        teacherSpeechRatio: (json['teacher_speech_ratio'] as num?)?.toDouble(),
        teacherSpeakers: ((json['teacher_speakers'] as List?) ?? const []).map((e) => e as String).toList(),
        keywords: ((json['keywords'] as List?) ?? const []).map((e) => e as String).toList(),
        topics: ((json['topics'] as List?) ?? const []).map((e) => Topic.fromJson(e as Map<String, dynamic>)).toList(),
        definitions: ((json['definitions'] as List?) ?? const [])
            .map((e) => Definition.fromJson(e as Map<String, dynamic>))
            .toList(),
        actionItems: ((json['action_items'] as List?) ?? const [])
            .map((e) => ActionItem.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
