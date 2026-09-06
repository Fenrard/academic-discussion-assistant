import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:scaitale_client/core/wav_encoder.dart';

void main() {
  group('wrapPcm16AsWav', () {
    test('produces a header of exactly 44 bytes plus the PCM data', () {
      final pcm = Uint8List.fromList(List.generate(100, (i) => i % 256));
      final wav = wrapPcm16AsWav(pcm);
      expect(wav.length, 44 + pcm.length);
    });

    test('RIFF/WAVE/fmt /data chunk IDs land at the canonical offsets', () {
      final pcm = Uint8List.fromList([1, 2, 3, 4]);
      final wav = wrapPcm16AsWav(pcm);
      String ascii(int start, int length) => String.fromCharCodes(wav.sublist(start, start + length));

      expect(ascii(0, 4), 'RIFF');
      expect(ascii(8, 4), 'WAVE');
      expect(ascii(12, 4), 'fmt ');
      expect(ascii(36, 4), 'data');
    });

    test('header fields are computed correctly for 16kHz mono 16-bit', () {
      final pcm = Uint8List(1000); // 1000 bytes of silence
      final wav = wrapPcm16AsWav(pcm, sampleRate: 16000, numChannels: 1, bitsPerSample: 16);
      final header = ByteData.sublistView(wav);

      expect(header.getUint32(4, Endian.little), 36 + 1000); // ChunkSize
      expect(header.getUint32(16, Endian.little), 16); // Subchunk1Size (PCM)
      expect(header.getUint16(20, Endian.little), 1); // AudioFormat (PCM)
      expect(header.getUint16(22, Endian.little), 1); // NumChannels
      expect(header.getUint32(24, Endian.little), 16000); // SampleRate
      expect(header.getUint32(28, Endian.little), 16000 * 1 * 2); // ByteRate
      expect(header.getUint16(32, Endian.little), 2); // BlockAlign
      expect(header.getUint16(34, Endian.little), 16); // BitsPerSample
      expect(header.getUint32(40, Endian.little), 1000); // Subchunk2Size (data length)
    });

    test('computes ByteRate/BlockAlign correctly for stereo', () {
      final wav = wrapPcm16AsWav(Uint8List(400), sampleRate: 48000, numChannels: 2, bitsPerSample: 16);
      final header = ByteData.sublistView(wav);

      expect(header.getUint16(22, Endian.little), 2); // NumChannels
      expect(header.getUint32(28, Endian.little), 48000 * 2 * 2); // ByteRate
      expect(header.getUint16(32, Endian.little), 4); // BlockAlign
    });

    test('handles an empty PCM payload without throwing', () {
      final wav = wrapPcm16AsWav(Uint8List(0));
      expect(wav.length, 44);
      final header = ByteData.sublistView(wav);
      expect(header.getUint32(40, Endian.little), 0);
    });

    test('preserves the PCM bytes verbatim after the header', () {
      final pcm = Uint8List.fromList([10, 20, 30, 40, 50]);
      final wav = wrapPcm16AsWav(pcm);
      expect(wav.sublist(44), pcm);
    });
  });
}
