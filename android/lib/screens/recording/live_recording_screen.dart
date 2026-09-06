import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:record/record.dart';

import '../../core/auth_controller.dart';
import '../../core/pcm_chunker.dart';
import '../../core/settings_controller.dart';
import '../../core/ws_transcribe_client.dart';
import '../../models/ws_messages.dart';
import '../transcript/transcript_screen.dart';

enum _Phase { idle, connecting, recording, stopping, error }

/// Live recording + real-time subtitles — the WS-driven screen. Sends the
/// `start` control frame, streams WAV-wrapped mic chunks, renders
/// `transcript_so_far` from each `chunk_result` as it arrives, sends `end`,
/// and navigates to the Transcript screen on `session_ended`.
class LiveRecordingScreen extends StatefulWidget {
  const LiveRecordingScreen({super.key});

  @override
  State<LiveRecordingScreen> createState() => _LiveRecordingScreenState();
}

class _LiveRecordingScreenState extends State<LiveRecordingScreen> {
  final _titleController = TextEditingController();
  final _recorder = AudioRecorder();
  final _wsClient = WsTranscribeClient();

  _Phase _phase = _Phase.idle;
  bool _consentConfirmed = false;
  String _liveTranscript = '';
  String? _error;
  StreamSubscription<Uint8List>? _micSubscription;
  StreamSubscription<WsServerMessage>? _wsSubscription;
  PcmChunker? _chunker;
  Timer? _elapsedTimer;
  Duration _elapsed = Duration.zero;

  @override
  void dispose() {
    _titleController.dispose();
    _micSubscription?.cancel();
    _wsSubscription?.cancel();
    _elapsedTimer?.cancel();
    _recorder.dispose();
    _wsClient.dispose();
    super.dispose();
  }

  Future<void> _start() async {
    if (!_consentConfirmed) return;

    setState(() {
      _phase = _Phase.connecting;
      _error = null;
      _liveTranscript = '';
    });

    final hasPermission = await _recorder.hasPermission();
    if (!mounted) return;
    if (!hasPermission) {
      setState(() {
        _phase = _Phase.error;
        _error = 'Microphone permission is required to record a session.';
      });
      return;
    }

    final auth = context.read<AuthController>();
    final settings = context.read<SettingsController>();
    final options = settings.pipelineOptions;

    try {
      await _wsClient.connect(
        baseUrl: settings.baseUrl,
        token: auth.token ?? '',
        onDisconnected: _handleUnexpectedDisconnect,
      );
    } catch (_) {
      setState(() {
        _phase = _Phase.error;
        _error = "Couldn't connect to the server. Check your connection and Settings.";
      });
      return;
    }

    _wsSubscription = _wsClient.messages.listen(_handleWsMessage, onError: (_) {});

    _wsClient.sendStart(StartFrame(
      title: _titleController.text.trim().isEmpty ? null : _titleController.text.trim(),
      consentConfirmed: _consentConfirmed,
      options: options.toJson(),
    ));
  }

  Future<void> _beginStreamingAudio(double chunkDurationSeconds) async {
    _chunker = PcmChunker(chunkDuration: Duration(milliseconds: (chunkDurationSeconds * 1000).round()));
    final pcmStream = await _recorder.startStream(
      const RecordConfig(encoder: AudioEncoder.pcm16bits, sampleRate: 16000, numChannels: 1),
    );
    _micSubscription = pcmStream.listen((data) {
      for (final chunk in _chunker!.add(data)) {
        if (chunk.shouldSend) _wsClient.sendChunk(chunk.wav);
      }
    });

    setState(() => _phase = _Phase.recording);
    _elapsed = Duration.zero;
    _elapsedTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      setState(() => _elapsed += const Duration(seconds: 1));
    });
  }

  void _handleWsMessage(WsServerMessage message) {
    switch (message) {
      case SessionStartedMessage():
        _beginStreamingAudio(context.read<SettingsController>().pipelineOptions.chunkDurationSeconds);
      case ChunkResultMessage():
        setState(() => _liveTranscript = message.transcriptSoFar);
      case WsErrorMessage():
        // Non-fatal — one chunk failed (e.g. a transient model error); recording continues.
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Chunk error: ${message.detail}')));
      case SessionEndedMessage():
        _elapsedTimer?.cancel();
        // The server closes the socket right after sending this message — a
        // graceful, expected closure, not a drop. Mark it as intentional
        // (synchronously, before any await) so the WS's onDone doesn't also
        // fire onDisconnected and pop back over the screen we're about to
        // push, which would otherwise race this navigation and undo it.
        unawaited(_wsClient.close());
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => TranscriptScreen(sessionId: message.sessionId)),
        );
    }
  }

  Future<void> _stop() async {
    setState(() => _phase = _Phase.stopping);
    await _micSubscription?.cancel();
    final leftover = _chunker?.flush();
    if (leftover != null && leftover.shouldSend) _wsClient.sendChunk(leftover.wav);
    await _recorder.stop();
    _wsClient.sendEnd();
    // Navigation happens from _handleWsMessage once session_ended arrives.
  }

  void _handleUnexpectedDisconnect() {
    if (!mounted) return;
    _elapsedTimer?.cancel();
    _micSubscription?.cancel();
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Connection lost — recording stopped. A partial transcript may be in your session list.')),
    );
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Live recording')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: _phase == _Phase.idle || _phase == _Phase.error ? _buildSetupForm() : _buildRecordingView(),
        ),
      ),
    );
  }

  Widget _buildSetupForm() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _titleController,
          decoration: const InputDecoration(labelText: 'Session title (optional)'),
        ),
        const SizedBox(height: 16),
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          value: _consentConfirmed,
          onChanged: (value) => setState(() => _consentConfirmed = value ?? false),
          title: const Text('I confirm consent to record this classroom session'),
        ),
        if (_error != null) ...[
          const SizedBox(height: 8),
          Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ],
        const SizedBox(height: 24),
        FilledButton.icon(
          onPressed: (_consentConfirmed && _phase != _Phase.connecting) ? _start : null,
          icon: _phase == _Phase.connecting
              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.mic),
          label: Text(_phase == _Phase.connecting ? 'Connecting…' : 'Start recording'),
        ),
      ],
    );
  }

  Widget _buildRecordingView() {
    final minutes = _elapsed.inMinutes.toString().padLeft(2, '0');
    final seconds = (_elapsed.inSeconds % 60).toString().padLeft(2, '0');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.fiber_manual_record, color: Theme.of(context).colorScheme.error, size: 16),
            const SizedBox(width: 8),
            Text('$minutes:$seconds', style: Theme.of(context).textTheme.titleLarge),
          ],
        ),
        const SizedBox(height: 16),
        Expanded(
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              borderRadius: BorderRadius.circular(12),
            ),
            child: SingleChildScrollView(
              reverse: true,
              child: Text(
                _liveTranscript.isEmpty ? 'Listening…' : _liveTranscript,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: _phase == _Phase.recording ? _stop : null,
          icon: const Icon(Icons.stop),
          label: Text(_phase == _Phase.stopping ? 'Finishing…' : 'Stop recording'),
          style: FilledButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error),
        ),
      ],
    );
  }
}
