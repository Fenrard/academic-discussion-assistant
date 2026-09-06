import 'dart:math' as math;
import 'dart:typed_data';

/// A lightweight, pure energy-based (RMS) voice activity detector — the
/// on-device half of CLAUDE.md's "Hybrid Edge/Server Design": "Local
/// (on-device): VAD + noise suppression — lightweight, always available."
/// This is that VAD half. It is deliberately not a learned model (no
/// Silero/WebRTC VAD bundled) — a simple energy gate is enough to decide
/// "does this chunk plausibly contain speech" before it ever leaves the
/// phone, at effectively zero CPU/battery cost and no native dependency.
///
/// [threshold] is a normalized RMS value (samples scaled to [-1, 1]) —
/// the default, 0.01 (~ -40 dBFS), is an **unvalidated heuristic default**,
/// not calibrated against real classroom audio: typical phone-mic
/// self-noise/room tone sits around -50 to -60 dBFS, while even soft or
/// distant classroom speech typically reads -35 to -20 dBFS, so this value
/// sits comfortably above self-noise and below real speech — biased toward
/// "send when uncertain" rather than "save bandwidth when uncertain", which
/// is the right bias for not losing real classroom speech. Same
/// "unmeasured until real data exists" caveat CLAUDE.md already carries for
/// `teacher_verification_threshold`.
///
/// [hasSpeech] windows the input into short (~30ms, a standard VAD frame
/// size) sub-frames and checks each one independently — never a single
/// average over the whole buffer. `PcmChunker` calls this on whole
/// `chunk_duration_seconds` blocks (2-10s), and a single short classroom
/// utterance ("yes sir") inside an otherwise-quiet 10s window would read as
/// silence under a naive whole-buffer average; windowing catches it as long
/// as it clears threshold anywhere in the buffer.
class LocalVad {
  final double threshold;
  final Duration frameDuration;
  final int sampleRate;

  const LocalVad({
    this.threshold = 0.01,
    this.frameDuration = const Duration(milliseconds: 30),
    this.sampleRate = 16000,
  });

  /// Returns true if any ~[frameDuration] sub-frame of [pcm16le] (mono,
  /// 16-bit little-endian samples) clears [threshold] RMS.
  bool hasSpeech(Uint8List pcm16le) {
    // An odd trailing byte can't form a full sample — drop it, not a bug.
    final usableLength = pcm16le.length - (pcm16le.length % 2);
    if (usableLength == 0) return false;

    final totalSamples = usableLength ~/ 2;
    final samplesPerFrame = (sampleRate * frameDuration.inMicroseconds / Duration.microsecondsPerSecond).round();
    // A buffer shorter than one frame (e.g. flush()'s partial tail) is
    // still evaluated, just as a single frame covering everything it has.
    final frameSampleCount = samplesPerFrame.clamp(1, totalSamples);

    final byteData = ByteData.sublistView(pcm16le, 0, usableLength);

    for (var frameStart = 0; frameStart < totalSamples; frameStart += frameSampleCount) {
      final frameEnd = (frameStart + frameSampleCount).clamp(0, totalSamples);
      var sumSquares = 0.0;
      for (var i = frameStart; i < frameEnd; i++) {
        final sample = byteData.getInt16(i * 2, Endian.little) / 32768.0;
        sumSquares += sample * sample;
      }
      final sampleCount = frameEnd - frameStart;
      if (sampleCount == 0) continue;
      final rms = math.sqrt(sumSquares / sampleCount);
      if (rms >= threshold) return true;
    }
    return false;
  }
}
