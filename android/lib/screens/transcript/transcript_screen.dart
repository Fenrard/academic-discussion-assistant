import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/api_exception.dart';
import '../../core/polling.dart';
import '../../models/session_models.dart';
import '../../widgets/error_banner.dart';
import '../../widgets/loading_view.dart';
import '../minutes/minutes_screen.dart';

/// Transcript view with search and match highlighting — client-side
/// substring matching over `transcript_segments`, per the backend contract's
/// explicit note that there's no server-side search endpoint.
class TranscriptScreen extends StatefulWidget {
  final String sessionId;

  const TranscriptScreen({super.key, required this.sessionId});

  @override
  State<TranscriptScreen> createState() => _TranscriptScreenState();
}

class _TranscriptScreenState extends State<TranscriptScreen> {
  bool _isLoading = true;
  String? _error;
  SessionDetail? _detail;
  String _query = '';
  final _searchController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final apiClient = context.read<ApiClient>();
      var detail = await apiClient.getSession(widget.sessionId);
      if (detail.isProcessing) {
        detail = await pollUntil<SessionDetail>(
          fetch: () => apiClient.getSession(widget.sessionId),
          isDone: (d) => !d.isProcessing,
          timeout: const Duration(minutes: 10),
        );
      }
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _isLoading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _isLoading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = "Can't reach the server. Check your connection and Settings.";
        _isLoading = false;
      });
    }
  }

  bool _matches(String text) => _query.isNotEmpty && text.toLowerCase().contains(_query.toLowerCase());

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    final matchCount = detail == null ? 0 : detail.transcriptSegments.where((s) => _matches(s.text)).length;

    return Scaffold(
      appBar: AppBar(
        title: Text(detail?.title?.isNotEmpty == true ? detail!.title! : 'Transcript'),
        actions: [
          if (detail?.minutes != null)
            IconButton(
              icon: const Icon(Icons.summarize_outlined),
              tooltip: 'Structured minutes',
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => MinutesScreen(sessionId: widget.sessionId)),
              ),
            ),
        ],
      ),
      body: _isLoading
          ? const LoadingView(message: 'Loading transcript…')
          : _error != null
              ? ErrorBanner(message: _error!, onRetry: _load)
              : Column(
                  children: [
                    Padding(
                      padding: const EdgeInsets.all(12),
                      child: TextField(
                        controller: _searchController,
                        decoration: InputDecoration(
                          prefixIcon: const Icon(Icons.search),
                          hintText: 'Search this transcript',
                          border: const OutlineInputBorder(),
                          suffixText: _query.isEmpty ? null : '$matchCount match${matchCount == 1 ? '' : 'es'}',
                        ),
                        onChanged: (value) => setState(() => _query = value),
                      ),
                    ),
                    Expanded(child: _buildSegmentList(detail!)),
                  ],
                ),
    );
  }

  Widget _buildSegmentList(SessionDetail detail) {
    if (detail.transcriptSegments.isEmpty) {
      return const Center(child: Text('No speech detected in this session.'));
    }

    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 12),
      itemCount: detail.transcriptSegments.length,
      itemBuilder: (context, index) {
        final segment = detail.transcriptSegments[index];
        final isMatch = _matches(segment.text);
        return Card(
          color: isMatch ? Theme.of(context).colorScheme.primaryContainer : null,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      '${segment.start.toStringAsFixed(1)}s – ${segment.end.toStringAsFixed(1)}s',
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                    const SizedBox(width: 8),
                    if (segment.speaker != null) Chip(label: Text(segment.speaker!), visualDensity: VisualDensity.compact),
                    if (segment.isTeacher == true) ...[
                      const SizedBox(width: 4),
                      Chip(
                        avatar: const Icon(Icons.school, size: 14),
                        label: Text(segment.teacherName ?? 'Teacher'),
                        visualDensity: VisualDensity.compact,
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 4),
                _highlightedText(segment.text, context),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _highlightedText(String text, BuildContext context) {
    if (_query.isEmpty) return Text(text);

    final lowerText = text.toLowerCase();
    final lowerQuery = _query.toLowerCase();
    final spans = <TextSpan>[];
    var start = 0;

    while (true) {
      final index = lowerText.indexOf(lowerQuery, start);
      if (index < 0) {
        spans.add(TextSpan(text: text.substring(start)));
        break;
      }
      spans.add(TextSpan(text: text.substring(start, index)));
      spans.add(TextSpan(
        text: text.substring(index, index + _query.length),
        style: const TextStyle(backgroundColor: Colors.yellow, fontWeight: FontWeight.bold),
      ));
      start = index + _query.length;
    }

    return RichText(text: TextSpan(style: DefaultTextStyle.of(context).style, children: spans));
  }
}
