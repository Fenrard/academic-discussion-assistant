import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:scaitale_client/core/local_vad.dart';

/// Builds a PCM16LE buffer of [sampleCount] samples all set to [value].
Uint8List constantSamples(int sampleCount, int value) {
  final bytes = Uint8List(sampleCount * 2);
  final data = ByteData.sublistView(bytes);
  for (var i = 0; i < sampleCount; i++) {
    data.setInt16(i * 2, value, Endian.little);
  }
  return bytes;
}

/// A full-scale square wave over [sampleCount] samples: alternating max/min
/// 16-bit values, RMS ~1.0 normalized -- unambiguously above any sane
/// VAD threshold.
Uint8List squareWave(int sampleCount) {
  final bytes = Uint8List(sampleCount * 2);
  final data = ByteData.sublistView(bytes);
  for (var i = 0; i < sampleCount; i++) {
    data.setInt16(i * 2, i.isEven ? 32767 : -32768, Endian.little);
  }
  return bytes;
}

void main() {
  group('LocalVad.hasSpeech', () {
    test('an empty buffer has no speech', () {
      expect(const LocalVad().hasSpeech(Uint8List(0)), isFalse);
    });

    test('a true-silence (all-zero) buffer has no speech', () {
      expect(const LocalVad().hasSpeech(Uint8List(3200)), isFalse);
    });

    test('a full-scale square wave has speech', () {
      expect(const LocalVad().hasSpeech(squareWave(1600)), isTrue);
    });

    test('hand-computed RMS: a constant sample value clears the default threshold', () {
      // RMS of a constant value is that value itself. 1000/32768 ~= 0.0305,
      // which clears the default threshold (0.01) but not a stricter one.
      final bytes = constantSamples(480, 1000); // 480 samples = one 30ms frame at 16kHz
      expect(const LocalVad().hasSpeech(bytes), isTrue);
      expect(const LocalVad(threshold: 0.05).hasSpeech(bytes), isFalse);
    });

    test('an odd trailing byte is ignored, not a crash', () {
      final evenBytes = constantSamples(10, 5000);
      final oddBytes = Uint8List(evenBytes.length + 1)..setRange(0, evenBytes.length, evenBytes);
      expect(const LocalVad().hasSpeech(oddBytes), const LocalVad().hasSpeech(evenBytes));
    });

    test('a buffer shorter than one frame is still evaluated as a single frame', () {
      // 4 bytes = 2 samples, far shorter than the default 30ms (480-sample) frame.
      final bytes = constantSamples(2, 20000);
      expect(const LocalVad().hasSpeech(bytes), isTrue);
    });

    test('windowing catches a short speech burst diluted by surrounding silence', () {
      // A whole-buffer average over this buffer would read well under
      // threshold (mostly silence) -- windowing must still catch the loud
      // sub-frame. This is exactly the regression this design guards
      // against: a real short classroom utterance inside an otherwise-quiet
      // multi-second chunk must not be missed.
      const totalSamples = 16000; // 1 second at 16kHz
      const burstStart = 8000;
      const burstLength = 480; // one 30ms frame
      final bytes = Uint8List(totalSamples * 2);
      final burst = squareWave(burstLength);
      bytes.setRange(burstStart * 2, (burstStart + burstLength) * 2, burst);
      expect(const LocalVad().hasSpeech(bytes), isTrue);
    });
  });
}
