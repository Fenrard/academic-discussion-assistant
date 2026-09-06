import 'package:flutter/material.dart';

/// Small colored chip for a session's or teacher enrollment's status —
/// pending/processing (amber, spinner), ready/completed (green check),
/// failed (red), and a few backend-specific session statuses in between.
class StatusBadge extends StatelessWidget {
  final String status;

  const StatusBadge({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    final (color, icon, label) = _presentation(status);
    return Chip(
      avatar: icon == null
          ? const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : Icon(icon, size: 16, color: color),
      label: Text(label),
      labelStyle: TextStyle(color: color, fontWeight: FontWeight.w600),
      backgroundColor: color.withValues(alpha: 0.12),
      side: BorderSide(color: color.withValues(alpha: 0.3)),
      visualDensity: VisualDensity.compact,
    );
  }

  (Color, IconData?, String) _presentation(String status) {
    switch (status) {
      case 'pending':
      case 'processing':
      case 'in_progress':
        return (Colors.amber.shade800, null, _titleCase(status));
      case 'ready':
      case 'completed':
        return (Colors.green.shade700, Icons.check_circle, _titleCase(status));
      case 'failed':
        return (Colors.red.shade700, Icons.error, _titleCase(status));
      case 'interrupted':
        return (Colors.orange.shade800, Icons.warning_amber, _titleCase(status));
      default:
        return (Colors.blueGrey, Icons.help_outline, _titleCase(status));
    }
  }

  String _titleCase(String s) => s.isEmpty ? s : '${s[0].toUpperCase()}${s.substring(1).replaceAll('_', ' ')}';
}
