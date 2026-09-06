import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:scaitale_client/core/pcm_chunker.dart';

Uint8List bytesOf(int length, [int start = 0]) => Uint8List.fromList(List.generate(length, (i) => (start + i) % 256));

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
      expect(emitted.first.length, 44 + 3200); // WAV header + PCM data
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
      expect(emitted.first.length, 44 + 3200);

      // The leftover 300 bytes plus a further 2900 completes the next chunk.
      final second = chunker.add(bytesOf(2900, 3500));
      expect(second, hasLength(1));
      expect(second.first.length, 44 + 3200);
    });

    test('a single large block spanning multiple chunks emits more than one chunk at once', () {
      final chunker = PcmChunker(chunkDuration: const Duration(milliseconds: 100));
      final emitted = chunker.add(bytesOf(3200 * 3 + 500));
      expect(emitted, hasLength(3));
      for (final chunk in emitted) {
        expect(chunk.length, 44 + 3200);
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
      expect(flushed!.length, 44 + 1200);
      expect(chunker.flush(), isNull); // buffer was cleared by the first flush
    });
  });
}
