import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/session_models.dart';
import 'status_badge.dart';

class SessionListTile extends StatelessWidget {
  final SessionSummary session;
  final VoidCallback onTap;
  final VoidCallback onDelete;

  const SessionListTile({super.key, required this.session, required this.onTap, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    final dateFormat = DateFormat.yMMMd().add_jm();
    final duration = session.durationSeconds;
    return Dismissible(
      key: ValueKey(session.id),
      direction: DismissDirection.endToStart,
      background: Container(
        color: Theme.of(context).colorScheme.error,
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: const Icon(Icons.delete, color: Colors.white),
      ),
      confirmDismiss: (_) async {
        final confirmed = await showDialog<bool>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: const Text('Delete session?'),
            content: const Text('This permanently removes the transcript and minutes. This cannot be undone.'),
            actions: [
              TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
              TextButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Delete')),
            ],
          ),
        );
        return confirmed ?? false;
      },
      onDismissed: (_) => onDelete(),
      child: ListTile(
        title: Text(session.title?.isNotEmpty == true ? session.title! : 'Untitled session'),
        subtitle: Text(
          duration != null ? '${dateFormat.format(session.createdAt)} · ${duration.round()}s' : dateFormat.format(session.createdAt),
        ),
        trailing: StatusBadge(status: session.status),
        onTap: onTap,
      ),
    );
  }
}
