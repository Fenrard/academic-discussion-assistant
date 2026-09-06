import 'dart:typed_data';

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
class PcmChunker {
  final int sampleRate;
  final int bytesPerSample;
  final int numChannels;
  final Duration chunkDuration;

  Uint8List _buffer = Uint8List(0);

  PcmChunker({
    this.sampleRate = 16000,
    this.bytesPerSample = 2,
    this.numChannels = 1,
    required this.chunkDuration,
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
  /// ready-to-send WAV-wrapped chunks (normally 0 or 1; a large input block —
  /// e.g. after a UI hiccup delivers several callbacks' worth at once — can
  /// complete more than one in a single call).
  List<Uint8List> add(Uint8List data) {
    final combined = Uint8List(_buffer.length + data.length)
      ..setRange(0, _buffer.length, _buffer)
      ..setRange(_buffer.length, _buffer.length + data.length, data);

    final target = bytesPerChunk;
    final chunks = <Uint8List>[];
    var offset = 0;
    while (combined.length - offset >= target) {
      final pcmChunk = combined.sublist(offset, offset + target);
      chunks.add(_wrap(pcmChunk));
      offset += target;
    }

    _buffer = combined.sublist(offset);
    return chunks;
  }

  /// Call when recording stops: emits whatever partial audio is left
  /// buffered as one final (usually short) WAV chunk, or null if the buffer
  /// is empty (e.g. stop landed exactly on a chunk boundary).
  Uint8List? flush() {
    if (_buffer.isEmpty) return null;
    final wav = _wrap(_buffer);
    _buffer = Uint8List(0);
    return wav;
  }

  Uint8List _wrap(Uint8List pcm) => wrapPcm16AsWav(
        pcm,
        sampleRate: sampleRate,
        numChannels: numChannels,
        bitsPerSample: bytesPerSample * 8,
      );
}
