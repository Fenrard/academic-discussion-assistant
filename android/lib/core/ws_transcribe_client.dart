import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/ws_messages.dart';

/// Drives `/ws/transcribe` for the live recording screen: connect with
/// `?token=` (WS can't set an Authorization header — see
/// backend/api/transcribe.py's docstring), send the `start` control frame,
/// stream binary WAV chunks, receive `chunk_result`/`error` frames, send
/// `end`, receive `session_ended`.
///
/// Deliberately does not attempt to reconnect on an unexpected drop — the
/// backend contract has no "resume session X" protocol, so a reconnect UX
/// would be fake. [onDisconnected] lets the recording screen surface that
/// and fall back to "check your session list" instead.
class WsTranscribeClient {
  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  final _messageController = StreamController<WsServerMessage>.broadcast();

  bool _closedByUs = false;

  Stream<WsServerMessage> get messages => _messageController.stream;

  /// Connects and waits for the underlying socket to actually be open.
  /// Throws (e.g. [WebSocketChannelException]) on failure — the caller
  /// should catch this the same way it catches [ApiException] elsewhere.
  Future<void> connect({
    required String baseUrl,
    required String token,
    void Function()? onDisconnected,
  }) async {
    _closedByUs = false;
    final uri = Uri.parse('${_toWsUrl(baseUrl)}/api/v1/ws/transcribe?token=$token');
    final channel = WebSocketChannel.connect(uri);
    await channel.ready;
    _channel = channel;

    _subscription = channel.stream.listen(
      _handleIncoming,
      onError: (Object error, StackTrace stack) {
        _messageController.addError(error, stack);
      },
      onDone: () {
        if (!_closedByUs) onDisconnected?.call();
      },
    );
  }

  void _handleIncoming(dynamic data) {
    if (data is! String) return; // server never sends binary frames back
    try {
      final json = jsonDecode(data) as Map<String, dynamic>;
      _messageController.add(WsServerMessage.fromJson(json));
    } catch (error, stack) {
      _messageController.addError(error, stack);
    }
  }

  void sendStart(StartFrame frame) => _channel?.sink.add(jsonEncode(frame.toJson()));

  void sendChunk(Uint8List wavBytes) => _channel?.sink.add(wavBytes);

  void sendEnd() => _channel?.sink.add(jsonEncode(const EndFrame().toJson()));

  Future<void> close() async {
    _closedByUs = true;
    await _subscription?.cancel();
    await _channel?.sink.close();
  }

  Future<void> dispose() async {
    await close();
    await _messageController.close();
  }

  static String _toWsUrl(String httpBaseUrl) {
    if (httpBaseUrl.startsWith('https://')) return 'wss://${httpBaseUrl.substring(8)}';
    if (httpBaseUrl.startsWith('http://')) return 'ws://${httpBaseUrl.substring(7)}';
    return httpBaseUrl;
  }
}
