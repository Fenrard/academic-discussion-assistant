import 'package:flutter/material.dart';

import '../models/pipeline_config.dart';

/// The Settings screen's advanced panel — outcome-framed labels, never raw
/// backend parameter names (CLAUDE.md: "Advanced settings panel with
/// outcome-framed labels"). Any edit here is reported via [onChanged] with a
/// full replacement PipelineOptions; SettingsController.updateOptions()
/// clears the selected preset to "Custom" as a result.
class AdvancedSettingsPanel extends StatelessWidget {
  final PipelineOptions options;
  final ValueChanged<PipelineOptions> onChanged;

  const AdvancedSettingsPanel({super.key, required this.options, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Reduce background noise'),
          subtitle: const Text('Helps in noisy classrooms; adds processing time'),
          value: options.enableDenoise,
          onChanged: (value) => onChanged(options.copyWith(enableDenoise: value)),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Skip silent gaps'),
          subtitle: const Text('Trims dead air from the transcript'),
          value: options.enableVad,
          onChanged: (value) => onChanged(options.copyWith(enableVad: value)),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Separate speakers'),
          subtitle: const Text('Label who said what (experimental)'),
          value: options.enableDiarization,
          onChanged: (value) => onChanged(options.copyWith(
            enableDiarization: value,
            numSpeakers: value ? null : () => null,
          )),
        ),
        if (options.enableDiarization)
          Padding(
            padding: const EdgeInsets.only(left: 16, bottom: 8),
            child: TextFormField(
              key: ValueKey(options.numSpeakers),
              initialValue: options.numSpeakers?.toString() ?? '',
              decoration: const InputDecoration(
                labelText: 'Expected number of speakers',
                helperText: 'Leave blank to auto-detect',
              ),
              keyboardType: TextInputType.number,
              onChanged: (text) {
                final parsed = int.tryParse(text);
                onChanged(options.copyWith(numSpeakers: () => parsed));
              },
            ),
          ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text("Prioritize teacher's voice"),
          subtitle: const Text('Requires teacher enrollment first'),
          value: options.enableTeacherVerification,
          onChanged: (value) => onChanged(options.copyWith(enableTeacherVerification: value)),
        ),
        const SizedBox(height: 16),
        Text('Accuracy vs. speed', style: Theme.of(context).textTheme.titleSmall),
        Text('Higher = more accurate, slower', style: Theme.of(context).textTheme.bodySmall),
        Slider(
          value: options.beamSize.toDouble().clamp(kMinBeamSize.toDouble(), kMaxBeamSize.toDouble()),
          min: kMinBeamSize.toDouble(),
          max: kMaxBeamSize.toDouble(),
          divisions: kMaxBeamSize - kMinBeamSize,
          label: options.beamSize.toString(),
          onChanged: (value) => onChanged(options.copyWith(beamSize: value.round())),
        ),
        const SizedBox(height: 8),
        Text('Live update frequency', style: Theme.of(context).textTheme.titleSmall),
        Text('Shorter = more frequent updates, more network use', style: Theme.of(context).textTheme.bodySmall),
        Slider(
          value: options.chunkDurationSeconds.clamp(kMinChunkDurationSeconds, kMaxChunkDurationSeconds),
          min: kMinChunkDurationSeconds,
          max: kMaxChunkDurationSeconds,
          divisions: (kMaxChunkDurationSeconds - kMinChunkDurationSeconds).round(),
          label: '${options.chunkDurationSeconds.round()}s',
          onChanged: (value) => onChanged(options.copyWith(chunkDurationSeconds: value)),
        ),
      ],
    );
  }
}
