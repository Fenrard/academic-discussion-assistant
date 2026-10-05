import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:record/record.dart';

import '../../core/api_client.dart';
import '../../core/api_exception.dart';
import '../../core/polling.dart';
import '../../models/teacher_models.dart';
import '../../widgets/error_banner.dart';
import '../../widgets/loading_view.dart';
import '../../widgets/status_badge.dart';

/// Teacher voice enrollment — records a short sample, uploads it, and polls
/// until the backend's async embedding-extraction task settles to
/// ready/failed (backend/api/teacher.py: POST /enroll returns 202
/// immediately, GET /teachers/{id} is polled for status).
class TeacherEnrollmentScreen extends StatefulWidget {
  const TeacherEnrollmentScreen({super.key});

  @override
  State<TeacherEnrollmentScreen> createState() => _TeacherEnrollmentScreenState();
}

class _TeacherEnrollmentScreenState extends State<TeacherEnrollmentScreen> {
  final _nameController = TextEditingController();
  final _recorder = AudioRecorder();

  bool _isLoading = true;
  String? _error;
  List<TeacherOut> _teachers = const [];

  bool _isRecording = false;
  bool _isSubmitting = false;
  String? _recordingPath;
  Duration _recordedDuration = Duration.zero;
  DateTime? _recordingStartedAt;

  @override
  void initState() {
    super.initState();
    _load();
    // Re-renders the submit button's enabled state as the name field changes.
    _nameController.addListener(_onNameChanged);
  }

  void _onNameChanged() => setState(() {});

  @override
  void dispose() {
    _nameController.removeListener(_onNameChanged);
    _nameController.dispose();
    _recorder.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final teachers = await context.read<ApiClient>().listTeachers();
      if (!mounted) return;
      setState(() {
        _teachers = teachers;
        _isLoading = false;
      });
      for (final teacher in teachers.where((t) => t.isPending)) {
        _pollTeacherStatus(teacher.id);
      }
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

  Future<void> _startRecording() async {
    final hasPermission = await _recorder.hasPermission();
    if (!hasPermission) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Microphone permission is required to enroll a teacher voice.')),
      );
      return;
    }

    final tempDir = await getTemporaryDirectory();
    final path = '${tempDir.path}/enrollment_${DateTime.now().millisecondsSinceEpoch}.wav';
    await _recorder.start(
      const RecordConfig(encoder: AudioEncoder.wav, sampleRate: 16000, numChannels: 1),
      path: path,
    );
    setState(() {
      _isRecording = true;
      _recordingPath = path;
      _recordingStartedAt = DateTime.now();
      _recordedDuration = Duration.zero;
    });
  }

  Future<void> _stopRecording() async {
    final path = await _recorder.stop();
    setState(() {
      _isRecording = false;
      _recordingPath = path ?? _recordingPath;
      if (_recordingStartedAt != null) {
        _recordedDuration = DateTime.now().difference(_recordingStartedAt!);
      }
    });
  }

  Future<void> _submit() async {
    final name = _nameController.text.trim();
    if (name.isEmpty || _recordingPath == null) return;

    final apiClient = context.read<ApiClient>();
    setState(() => _isSubmitting = true);
    try {
      final bytes = await File(_recordingPath!).readAsBytes();
      final teacher = await apiClient.enrollTeacher(name, bytes, filename: 'enrollment.wav');
      if (!mounted) return;
      setState(() {
        _teachers = [teacher, ..._teachers];
        _nameController.clear();
        _recordingPath = null;
        _recordedDuration = Duration.zero;
      });
      _pollTeacherStatus(teacher.id);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Enrollment failed: ${e.message}')));
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Can't reach the server.")));
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  Future<void> _pollTeacherStatus(String id) async {
    try {
      final updated = await pollUntil<TeacherOut>(
        fetch: () => context.read<ApiClient>().getTeacher(id),
        isDone: (t) => !t.isPending,
      );
      if (!mounted) return;
      setState(() {
        _teachers = _teachers.map((t) => t.id == id ? updated : t).toList();
      });
    } catch (_) {
      // Timed out or a transient error — the teacher stays "pending" in the
      // list; a manual pull-to-refresh (_load) will re-check its status.
    }
  }

  Future<void> _delete(TeacherOut teacher) async {
    try {
      await context.read<ApiClient>().deleteTeacher(teacher.id);
      if (!mounted) return;
      setState(() => _teachers = _teachers.where((t) => t.id != teacher.id).toList());
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not delete: ${e.message}')));
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Could not delete — can't reach the server.")),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Teacher voice enrollment')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _buildEnrollForm(),
            const Divider(height: 32),
            Text('Enrolled teachers', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (_isLoading)
              const LoadingView()
            else if (_error != null)
              ErrorBanner(message: _error!, onRetry: _load)
            else if (_teachers.isEmpty)
              const Padding(padding: EdgeInsets.all(16), child: Text('No teachers enrolled yet.'))
            else
              ..._teachers.map(
                (teacher) => Card(
                  child: ListTile(
                    title: Text(teacher.name),
                    subtitle: teacher.isFailed && teacher.errorDetail != null ? Text(teacher.errorDetail!) : null,
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        StatusBadge(status: teacher.status),
                        IconButton(
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () => _delete(teacher),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildEnrollForm() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Enroll a new teacher voice', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 4),
            const Text('Record about 10–15 seconds of the teacher speaking clearly.'),
            const SizedBox(height: 12),
            TextField(
              controller: _nameController,
              decoration: const InputDecoration(labelText: 'Teacher name'),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                FilledButton.icon(
                  onPressed: _isSubmitting ? null : (_isRecording ? _stopRecording : _startRecording),
                  icon: Icon(_isRecording ? Icons.stop : Icons.mic),
                  label: Text(_isRecording ? 'Stop recording' : 'Record sample'),
                ),
                const SizedBox(width: 12),
                if (!_isRecording && _recordingPath != null)
                  Text('Recorded ${_recordedDuration.inSeconds}s'),
              ],
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: (_isSubmitting || _isRecording || _recordingPath == null || _nameController.text.trim().isEmpty)
                  ? null
                  : _submit,
              child: _isSubmitting
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Submit enrollment'),
            ),
          ],
        ),
      ),
    );
  }
}
