import 'package:flutter_test/flutter_test.dart';
import 'package:scaitale_client/models/pipeline_config.dart';

void main() {
  group('PipelinePresets.resolve', () {
    test('fast preset matches expected values', () {
      final options = PipelinePresets.resolve(Preset.fast);
      expect(options.enableDenoise, false);
      expect(options.enableVad, true);
      expect(options.enableDiarization, false);
      expect(options.enableTeacherVerification, false);
      expect(options.beamSize, 1);
      expect(options.chunkDurationSeconds, 2.0);
    });

    test('balanced preset matches backend schema defaults exactly', () {
      final options = PipelinePresets.resolve(Preset.balanced);
      expect(options.enableVad, true);
      expect(options.beamSize, 5);
      expect(options.chunkDurationSeconds, 3.0);
      expect(options.numSpeakers, isNull);
    });

    test('accurate preset enables every extra stage', () {
      final options = PipelinePresets.resolve(Preset.accurate);
      expect(options.enableDenoise, true);
      expect(options.enableDiarization, true);
      expect(options.enableTeacherVerification, true);
      expect(options.beamSize, 8);
      expect(options.chunkDurationSeconds, 5.0);
    });
  });

  group('PipelineOptions.toJson', () {
    test('key names match backend/schemas/pipeline.py exactly', () {
      final json = PipelinePresets.balanced.toJson();
      expect(json.keys.toSet(), {
        'enable_denoise',
        'enable_vad',
        'enable_diarization',
        'enable_teacher_verification',
        'num_speakers',
        'beam_size',
        'chunk_duration_seconds',
      });
    });

    test('round-trips through fromJson', () {
      const original = PipelineOptions(
        enableDenoise: true,
        enableVad: false,
        enableDiarization: true,
        enableTeacherVerification: false,
        numSpeakers: 3,
        beamSize: 7,
        chunkDurationSeconds: 4.5,
      );
      final roundTripped = PipelineOptions.fromJson(original.toJson());
      expect(roundTripped, original);
    });
  });

  group('PipelineOptions.copyWith', () {
    test('overrides only the given fields', () {
      final updated = PipelinePresets.balanced.copyWith(beamSize: 9);
      expect(updated.beamSize, 9);
      expect(updated.enableVad, PipelinePresets.balanced.enableVad);
    });

    test('numSpeakers can be explicitly cleared to null via the wrapped setter', () {
      final withSpeakers = PipelinePresets.balanced.copyWith(numSpeakers: () => 4);
      expect(withSpeakers.numSpeakers, 4);

      final cleared = withSpeakers.copyWith(numSpeakers: () => null);
      expect(cleared.numSpeakers, isNull);
    });
  });

  group('PipelinePresets.matching', () {
    test('identifies an exact preset match', () {
      expect(PipelinePresets.matching(PipelinePresets.fast), Preset.fast);
      expect(PipelinePresets.matching(PipelinePresets.balanced), Preset.balanced);
      expect(PipelinePresets.matching(PipelinePresets.accurate), Preset.accurate);
    });

    test('returns null for a hand-edited (custom) configuration', () {
      final custom = PipelinePresets.balanced.copyWith(beamSize: 2);
      expect(PipelinePresets.matching(custom), isNull);
    });
  });
}
