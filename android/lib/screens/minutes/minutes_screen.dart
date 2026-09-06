import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/api_client.dart';
import '../../core/api_exception.dart';
import '../../models/minutes_models.dart';
import '../../widgets/error_banner.dart';
import '../../widgets/loading_view.dart';

/// Structured minutes view + export — renders the four required sections
/// (key points via Topics, topics, definitions, tasks via action items),
/// null-safe on the fields older sessions won't have (teacher_speech_ratio,
/// teacher_speakers, definitions — see backend/api/minutes.py's own
/// `.get()`-defensive rendering, mirrored here).
class MinutesScreen extends StatefulWidget {
  final String sessionId;

  const MinutesScreen({super.key, required this.sessionId});

  @override
  State<MinutesScreen> createState() => _MinutesScreenState();
}

class _MinutesScreenState extends State<MinutesScreen> {
  bool _isLoading = true;
  String? _error;
  bool _notYetGenerated = false;
  Minutes? _minutes;
  bool _isExporting = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _error = null;
      _notYetGenerated = false;
    });
    try {
      final json = await context.read<ApiClient>().getMinutes(widget.sessionId);
      if (!mounted) return;
      setState(() {
        _minutes = Minutes.fromJson(json);
        _isLoading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        if (e.isConflict) {
          _notYetGenerated = true;
        } else {
          _error = e.message;
        }
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = "Can't reach the server. Check your connection and Settings.";
        _isLoading = false;
      });
    }
  }

  Future<void> _export(String format) async {
    setState(() => _isExporting = true);
    try {
      final body = await context.read<ApiClient>().exportMinutes(widget.sessionId, format: format);
      await SharePlus.instance.share(ShareParams(text: body, subject: 'Classroom minutes'));
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Export failed: ${e.message}')));
    } finally {
      if (mounted) setState(() => _isExporting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Structured minutes'),
        actions: [
          if (_minutes != null)
            PopupMenuButton<String>(
              icon: _isExporting
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.ios_share),
              onSelected: _isExporting ? null : _export,
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'markdown', child: Text('Share as Markdown')),
                PopupMenuItem(value: 'txt', child: Text('Share as plain text')),
              ],
            ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) return const LoadingView(message: 'Loading minutes…');
    if (_notYetGenerated) {
      return const Center(child: Text('Minutes have not been generated yet for this session.'));
    }
    if (_error != null) return ErrorBanner(message: _error!, onRetry: _load);

    final minutes = _minutes!;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _buildHeader(minutes),
        const SizedBox(height: 16),
        if (minutes.keywords.isNotEmpty) ...[
          Text('Keywords', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, children: minutes.keywords.map((k) => Chip(label: Text(k))).toList()),
          const SizedBox(height: 20),
        ],
        Text('Topics', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (minutes.topics.isEmpty)
          const Text('No topics detected.')
        else
          ...minutes.topics.map((topic) => _buildTopicCard(topic)),
        const SizedBox(height: 20),
        Text('Definitions', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (minutes.definitions.isEmpty)
          const Text('None detected.')
        else
          ...minutes.definitions.map(
            (d) => Card(
              child: ListTile(
                title: Text(d.term, style: const TextStyle(fontWeight: FontWeight.bold)),
                subtitle: Text(d.definition),
              ),
            ),
          ),
        const SizedBox(height: 20),
        Text('Action items', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (minutes.actionItems.isEmpty)
          const Text('None detected.')
        else
          ...minutes.actionItems.map(
            (item) => Card(
              child: ListTile(
                leading: const Icon(Icons.task_alt),
                title: Text(item.text),
                subtitle: Text('${item.speaker} · ${item.start.toStringAsFixed(1)}s'),
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildHeader(Minutes minutes) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Generated: ${minutes.generatedAt}', style: Theme.of(context).textTheme.bodySmall),
            Text('Duration: ${minutes.durationSeconds.round()}s', style: Theme.of(context).textTheme.bodySmall),
            Text(
              'Participants: ${minutes.participants.isEmpty ? 'Unknown' : minutes.participants.join(', ')}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            if (minutes.teacherSpeechRatio != null) ...[
              const SizedBox(height: 4),
              Text(
                'Teacher speech: ${(minutes.teacherSpeechRatio! * 100).toStringAsFixed(1)}%'
                '${minutes.teacherSpeakers.isEmpty ? '' : ' (${minutes.teacherSpeakers.join(', ')})'}',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildTopicCard(Topic topic) {
    return Card(
      child: ExpansionTile(
        title: Text(topic.label),
        subtitle: Text('${topic.start.toStringAsFixed(1)}s – ${topic.end.toStringAsFixed(1)}s'),
        children: topic.keyPoints
            .map((point) => Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [const Text('•  '), Expanded(child: Text(point))],
                  ),
                ))
            .toList(),
      ),
    );
  }
}
