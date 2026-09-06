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
class PcmChunker {
  final int sampleRate;
  final int bytesPerSample;
  final int numChannels;
  final Duration chunkDuration;
  final LocalVad vad;

  Uint8List _buffer = Uint8List(0);
  bool _lastChunkHadSpeech = true;

  PcmChunker({
    this.sampleRate = 16000,
    this.bytesPerSample = 2,
    this.numChannels = 1,
    required this.chunkDuration,
    this.vad = const LocalVad(),
  });

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
  /// complete more than one in a single call). Each record's `shouldSend`
  /// reflects the VAD + hangover decision for that chunk; `wav` is always
  /// fully built regardless, so a caller that wants every chunk regardless
  /// of gating can still get it.
  List<({Uint8List wav, bool shouldSend})> add(Uint8List data) {
    final combined = Uint8List(_buffer.length + data.length)
      ..setRange(0, _buffer.length, _buffer)
      ..setRange(_buffer.length, _buffer.length + data.length, data);

    final target = bytesPerChunk;
    final chunks = <({Uint8List wav, bool shouldSend})>[];
    var offset = 0;
    while (combined.length - offset >= target) {
      final pcmChunk = combined.sublist(offset, offset + target);
      chunks.add(_wrapAndGate(pcmChunk));
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
    final result = _wrapAndGate(_buffer);
    _buffer = Uint8List(0);
    return result;
  }

  ({Uint8List wav, bool shouldSend}) _wrapAndGate(Uint8List pcm) {
    // VAD runs on the raw PCM, never on the already-WAV-wrapped bytes — the
    // 44-byte RIFF header would corrupt the RMS read.
    final hasSpeech = vad.hasSpeech(pcm);
    final shouldSend = hasSpeech || _lastChunkHadSpeech;
    _lastChunkHadSpeech = hasSpeech;
    return (wav: _wrap(pcm), shouldSend: shouldSend);
  }

  Uint8List _wrap(Uint8List pcm) => wrapPcm16AsWav(
        pcm,
        sampleRate: sampleRate,
        numChannels: numChannels,
        bitsPerSample: bytesPerSample * 8,
      );
}
