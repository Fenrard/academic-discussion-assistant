import 'dart:typed_data';

import 'local_vad.dart';
import 'wav_encoder.dart';

/// Buffers headerless PCM16LE bytes arriving from `record`'s
/// `startStream()` (whose delivery size/timing is driven by the platform
/// audio callback, not by us) into fixed-duration, self-contained WAV
/// chunks matching the user's `chunk_duration_seconds` setting.
///
/// Deliberately a synchronous "feed bytes, get back ready chunks" API
/// (not a `Stream` transformer) — simpler to drive from a stream listener
/// callback and, more importantly, trivially deterministic to unit test: no
/// `BytesBuilder.takeBytes()` reset pitfall (that clears the whole buffer,
/// losing any partial remainder), no async scheduling to account for.
///
/// Also owns the on-device VAD gating decision — CLAUDE.md's "Hybrid
/// Edge/Server Design": "Local (on-device): VAD... lightweight, always
/// available." Each returned chunk carries a `shouldSend` flag alongside
/// its WAV bytes: [vad] decides per-chunk whether it plausibly contains
/// speech, and this class applies a 1-chunk "hangover" on top (a chunk
/// immediately following detected speech is still sent even if it reads
/// quiet itself) so real speech trailing across the coarse
/// `chunk_duration_seconds` boundary isn't clipped. The very first chunk of
/// a session is always sent regardless of its own content — nothing is
/// ever dropped before the filter has seen anything.
///
/// On top of that, [keepAliveInterval] bounds the longest possible gap
/// between sent chunks: a real classroom can have a genuinely long quiet
/// stretch (students working silently, a break), and gating every chunk
/// during it would leave the WebSocket completely idle for that whole
/// time — long enough for a NAT/carrier/proxy idle-connection timeout to
/// silently drop it, which the client only discovers via a disconnect
/// event that ends the session early. Forcing a real (silent) chunk
/// through periodically keeps the connection demonstrably alive without
/// any new wire protocol — it's a normal chunk the server already knows
/// how to handle, just an infrequent one. Default 30s is a heuristic
/// (common NAT/proxy idle timeouts range from ~30s to a few minutes),
/// same "unvalidated against a real deployment" caveat this file already
/// carries for the VAD threshold; pass `null` to disable it entirely.
class PcmChunker {
  final int sampleRate;
  final int bytesPerSample;
  final int numChannels;
  final Duration chunkDuration;
  final LocalVad vad;
  final Duration? keepAliveInterval;

  Uint8List _buffer = Uint8List(0);
  bool _lastChunkHadSpeech = true;
  int _chunksSinceLastSend = 0;

  PcmChunker({
    this.sampleRate = 16000,
    this.bytesPerSample = 2,
    this.numChannels = 1,
    required this.chunkDuration,
    LocalVad? vad,
    this.keepAliveInterval = const Duration(seconds: 30),
  }) : vad = vad ?? LocalVad(sampleRate: sampleRate); // derived, not a bare default — see below

  /// Bytes needed for one full chunk at the configured duration/format.
  int get bytesPerChunk {
    final frameSize = bytesPerSample * numChannels;
    final raw = sampleRate * frameSize * chunkDuration.inMicroseconds / Duration.microsecondsPerSecond;
    final rounded = raw.round();
    // Never target less than one full sample frame, even for a near-zero duration.
    return rounded < frameSize ? frameSize : rounded;
  }

  /// Feed one arrived block of raw PCM bytes. Returns zero or more
  /// ready-to-send records (normally 0 or 1; a large input block — e.g.
  /// after a UI hiccup delivers several callbacks' worth at once — can
  /// complete more than one in a single call). `wav` is only ever the real
  /// wrapped WAV bytes when `shouldSend` is true — building it for a chunk
  /// that's about to be discarded would be pure waste, since nothing
  /// currently reads `wav` on a gated-out chunk; it's `Uint8List(0)`
  /// otherwise.
  List<({Uint8List wav, bool shouldSend})> add(Uint8List data) {
    final combined = Uint8List(_buffer.length + data.length)
      ..setRange(0, _buffer.length, _buffer)
      ..setRange(_buffer.length, _buffer.length + data.length, data);

    final target = bytesPerChunk;
    final chunks = <({Uint8List wav, bool shouldSend})>[];
    var offset = 0;
    while (combined.length - offset >= target) {
      final pcmChunk = combined.sublist(offset, offset + target);
      chunks.add(_gate(pcmChunk));
      offset += target;
    }

    _buffer = combined.sublist(offset);
    return chunks;
  }

  /// Call when recording stops: emits whatever partial audio is left
  /// buffered as one final (usually short) record, or null if the buffer
  /// is empty (e.g. stop landed exactly on a chunk boundary).
  ({Uint8List wav, bool shouldSend})? flush() {
    if (_buffer.isEmpty) return null;
    final result = _gate(_buffer);
    _buffer = Uint8List(0);
    return result;
  }

  ({Uint8List wav, bool shouldSend}) _gate(Uint8List pcm) {
    // VAD runs on the raw PCM, never on the already-WAV-wrapped bytes — the
    // 44-byte RIFF header would corrupt the RMS read.
    final hasSpeech = vad.hasSpeech(pcm);
    var shouldSend = hasSpeech || _lastChunkHadSpeech;

    final keepAlive = keepAliveInterval;
    if (!shouldSend && keepAlive != null) {
      final keepAliveChunks = (keepAlive.inMilliseconds / chunkDuration.inMilliseconds).ceil().clamp(1, 1 << 30);
      if (_chunksSinceLastSend + 1 >= keepAliveChunks) {
        shouldSend = true; // forced keepalive heartbeat — still real (silent) audio, no new protocol
      }
    }

    _lastChunkHadSpeech = hasSpeech;
    _chunksSinceLastSend = shouldSend ? 0 : _chunksSinceLastSend + 1;
    return (wav: shouldSend ? _wrap(pcm) : Uint8List(0), shouldSend: shouldSend);
  }

  Uint8List _wrap(Uint8List pcm) => wrapPcm16AsWav(
        pcm,
        sampleRate: sampleRate,
        numChannels: numChannels,
        bitsPerSample: bytesPerSample * 8,
      );
}
