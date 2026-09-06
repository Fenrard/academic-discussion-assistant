import 'package:flutter/material.dart';

import '../models/pipeline_config.dart';

/// Fast / Balanced / Accurate selector, plus a read-only "Custom" state when
/// the advanced panel has been hand-edited away from any of the three named
/// presets (see SettingsController.updateOptions).
class PipelinePresetSelector extends StatelessWidget {
  final Preset? selected;
  final ValueChanged<Preset> onSelected;

  const PipelinePresetSelector({super.key, required this.selected, required this.onSelected});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SegmentedButton<Preset>(
          segments: Preset.values.map((p) => ButtonSegment(value: p, label: Text(p.label))).toList(),
          selected: selected == null ? {} : {selected!},
          emptySelectionAllowed: true,
          onSelectionChanged: (set) {
            if (set.isNotEmpty) onSelected(set.first);
          },
        ),
        if (selected == null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              'Custom — one or more settings below were changed by hand.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
      ],
    );
  }
}
