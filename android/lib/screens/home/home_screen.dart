import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/api_exception.dart';
import '../../core/auth_controller.dart';
import '../../models/session_models.dart';
import '../../widgets/error_banner.dart';
import '../../widgets/loading_view.dart';
import '../../widgets/session_list_tile.dart';
import '../enrollment/teacher_enrollment_screen.dart';
import '../recording/live_recording_screen.dart';
import '../settings/settings_screen.dart';
import '../transcript/transcript_screen.dart';

/// Home / session library — the app's landing screen once authenticated.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  bool _isLoading = true;
  String? _error;
  List<SessionSummary> _sessions = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final sessions = await context.read<ApiClient>().listSessions();
      if (!mounted) return;
      setState(() {
        _sessions = sessions;
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

  Future<void> _delete(SessionSummary session) async {
    try {
      await context.read<ApiClient>().deleteSession(session.id);
      if (!mounted) return;
      setState(() => _sessions = _sessions.where((s) => s.id != session.id).toList());
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not delete session: ${e.message}')));
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Could not delete session — can't reach the server.")),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Scaitale'),
        actions: [
          IconButton(
            icon: const Icon(Icons.record_voice_over_outlined),
            tooltip: 'Teacher voice enrollment',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const TeacherEnrollmentScreen())),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            tooltip: 'Settings',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SettingsScreen())),
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Log out',
            onPressed: () => context.read<AuthController>().logout(),
          ),
        ],
      ),
      body: _buildBody(),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const LiveRecordingScreen()));
          if (mounted) _load();  // a 401 during recording can force-logout and dispose this screen mid-await
        },
        icon: const Icon(Icons.mic),
        label: const Text('New session'),
      ),
    );
  }

  Widget _buildBody() {
    if (_isLoading) return const LoadingView(message: 'Loading sessions…');
    if (_error != null) return ErrorBanner(message: _error!, onRetry: _load);
    if (_sessions.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.mic_none, size: 48, color: Theme.of(context).colorScheme.outline),
              const SizedBox(height: 12),
              const Text('No sessions yet — start a recording to begin.', textAlign: TextAlign.center),
            ],
          ),
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.separated(
        itemCount: _sessions.length,
        separatorBuilder: (_, _) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final session = _sessions[index];
          return SessionListTile(
            session: session,
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => TranscriptScreen(sessionId: session.id)),
            ),
            onDelete: () => _delete(session),
          );
        },
      ),
    );
  }
}
