import 'dart:typed_data';

/// Wraps headerless PCM16LE samples in a canonical 44-byte RIFF/WAVE header,
/// producing a complete, self-contained WAV file in memory.
///
/// This exists because `record` package's `startStream()` (used for live
/// chunked recording — see `pcm_chunker.dart`) only ever emits headerless raw
/// PCM via `AudioEncoder.pcm16bits`; a true streaming WAV encoder isn't
/// possible in the first place, since a WAV header's total-length field can't
/// be known until recording stops. The backend's WS handler
/// (`backend/api/transcribe.py`) writes each binary frame straight to a
/// `.wav` temp file and hands it to FFmpeg, which sniffs the container from
/// its bytes — so every frame sent over the wire must be a valid,
/// self-contained WAV file, not a headerless PCM fragment. This function is
/// the one place that guarantee is enforced.
Uint8List wrapPcm16AsWav(
  Uint8List pcmData, {
  int sampleRate = 16000,
  int numChannels = 1,
  int bitsPerSample = 16,
}) {
  final byteRate = sampleRate * numChannels * bitsPerSample ~/ 8;
  final blockAlign = numChannels * bitsPerSample ~/ 8;
  final dataLength = pcmData.length;
  final chunkSize = 36 + dataLength;

  final header = ByteData(44);
  void writeAscii(int offset, String text) {
    for (var i = 0; i < text.length; i++) {
      header.setUint8(offset + i, text.codeUnitAt(i));
    }
  }

  writeAscii(0, 'RIFF');
  header.setUint32(4, chunkSize, Endian.little);
  writeAscii(8, 'WAVE');

  writeAscii(12, 'fmt ');
  header.setUint32(16, 16, Endian.little); // Subchunk1Size (16 = PCM)
  header.setUint16(20, 1, Endian.little); // AudioFormat (1 = PCM, uncompressed)
  header.setUint16(22, numChannels, Endian.little);
  header.setUint32(24, sampleRate, Endian.little);
  header.setUint32(28, byteRate, Endian.little);
  header.setUint16(32, blockAlign, Endian.little);
  header.setUint16(34, bitsPerSample, Endian.little);

  writeAscii(36, 'data');
  header.setUint32(40, dataLength, Endian.little);

  final wavBytes = Uint8List(44 + dataLength);
  wavBytes.setRange(0, 44, header.buffer.asUint8List());
  wavBytes.setRange(44, 44 + dataLength, pcmData);
  return wavBytes;
}
