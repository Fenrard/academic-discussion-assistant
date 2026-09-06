import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:scaitale_client/core/pcm_chunker.dart';

Uint8List bytesOf(int length, [int start = 0]) => Uint8List.fromList(List.generate(length, (i) => (start + i) % 256));

/// True digital silence: all-zero PCM16 samples, RMS exactly 0.
Uint8List silentBytes(int length) => Uint8List(length);

/// A full-scale square wave: alternating max/min 16-bit samples, RMS ~1.0
/// normalized — unambiguously above any sane VAD threshold.
Uint8List loudBytes(int length) {
  final bytes = Uint8List(length);
  final data = ByteData.sublistView(bytes);
  for (var i = 0; i + 1 < length; i += 2) {
    data.setInt16(i, (i ~/ 2).isEven ? 32767 : -32768, Endian.little);
  }
  return bytes;
}

void main() {
  group('PcmChunker.bytesPerChunk', () {
    test('computes the expected byte count for 16kHz mono 16-bit, 100ms', () {
      final chunker = PcmChunker(chunkDuration: const Duration(milliseconds: 100));
      // 16000 samples/s * 2 bytes/sample * 1 channel * 0.1s = 3200 bytes
      expect(chunker.bytesPerChunk, 3200);
    });
  });

  group('PcmChunker.add', () {
    test('feeding exactly one chunk worth of bytes emits exactly one WAV chunk', () {
      final chunker = PcmChunker(chunkDuration: const Duration(milliseconds: 100));
      final emitted = chunker.add(bytesOf(3200));
      expect(emitted, hasLength(1));
      expect(emitted.first.wav.length, 44 + 3200); // WAV header + PCM data
    });

    test('feeding less than one chunk emits nothing and buffers the remainder', () {
      final chunker = PcmChunker(chunkDuration: const Duration(milliseconds: 100));
      final emitted = chunker.add(bytesOf(1000));
      expect(emitted, isEmpty);
    });

    test('remainder carries over across multiple add() calls', () {
      final chunker = PcmChunker(chunkDuration: const Duration(milliseconds: 100));
      expect(chunker.add(bytesOf(2000)), isEmpty);
      // 2000 + 1500 = 3500 >= 3200 -> exactly one chunk, 300 bytes left over.
      final emitted = chunker.add(bytesOf(1500, 2000));
      expect(emitted, hasLength(1));
      expect(emitted.first.wav.length, 44 + 3200);

      // The leftover 300 bytes plus a further 2900 completes the next chunk.
      final second = chunker.add(bytesOf(2900, 3500));
      expect(second, hasLength(1));
      expect(second.first.wav.length, 44 + 3200);
    });

    test('a single large block spanning multiple chunks emits more than one chunk at once', () {
      final chunker = PcmChunker(chunkDuration: const Duration(milliseconds: 100));
      final emitted = chunker.add(bytesOf(3200 * 3 + 500));
      expect(emitted, hasLength(3));
      for (final chunk in emitted) {
        expect(chunk.wav.length, 44 + 3200);
      }
    });

    test('never targets less than one full sample frame for a near-zero duration', () {
      final chunker = PcmChunker(chunkDuration: Duration.zero);
      expect(chunker.bytesPerChunk, greaterThanOrEqualTo(2)); // bytesPerSample(2) * numChannels(1)
    });
  });

  group('PcmChunker.flush', () {
    test('returns null when nothing is buffered', () {
      final chunker = PcmChunker(chunkDuration: const Duration(milliseconds: 100));
      expect(chunker.flush(), isNull);
    });

    test('emits a short final WAV chunk for a partial buffer, then clears it', () {
      final chunker = PcmChunker(chunkDuration: const Duration(milliseconds: 100));
      chunker.add(bytesOf(1200));
      final flushed = chunker.flush();
      expect(flushed, isNotNull);
      expect(flushed!.wav.length, 44 + 1200);
      expect(chunker.flush(), isNull); // buffer was cleared by the first flush
    });
  });

  group('PcmChunker VAD gating', () {
    // One continuous sequence on a single instance — the hangover policy is
    // stateful, so isolated single-add() tests would need priming anyway.
    // Each add() below is fed exactly bytesPerChunk bytes so each call
    // returns exactly one record to inspect.
    test('first chunk always sent, then gates on speech with a 1-chunk hangover', () {
      final chunker = PcmChunker(chunkDuration: const Duration(milliseconds: 100));
      const size = 3200;

      // 1. First-ever chunk: sent regardless of content, before the VAD has
      //    any history — even though it's pure silence.
      final first = chunker.add(silentBytes(size));
      expect(first.single.shouldSend, isTrue);

      // 2. Baseline established: silence with no recent speech -> not sent.
      final second = chunker.add(silentBytes(size));
      expect(second.single.shouldSend, isFalse);

      // 3. Real detection: a loud chunk is sent.
      final third = chunker.add(loudBytes(size));
      expect(third.single.shouldSend, isTrue);

      // 4. Hangover: silence immediately following detected speech is still sent.
      final fourth = chunker.add(silentBytes(size));
      expect(fourth.single.shouldSend, isTrue);

      // 5. Hangover expired: two chunks after speech, silence is not sent.
      final fifth = chunker.add(silentBytes(size));
      expect(fifth.single.shouldSend, isFalse);
    });

    test('flush() applies the same gating decision to the trailing partial chunk', () {
      final chunker = PcmChunker(chunkDuration: const Duration(milliseconds: 100));
      // Establish "no recent speech" first.
      chunker.add(silentBytes(3200));
      chunker.add(silentBytes(3200));

      chunker.add(silentBytes(1000)); // partial, buffered
      final flushed = chunker.flush();
      expect(flushed, isNotNull);
      expect(flushed!.shouldSend, isFalse);
    });
  });
}
