import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_controller.dart';
import '../../core/settings_controller.dart';
import '../../widgets/advanced_settings_panel.dart';
import '../../widgets/pipeline_preset_selector.dart';

/// Settings: server base URL, preset selector, advanced panel, logout. Every
/// field writes straight through to SettingsController on change — no
/// separate Save/Cancel flow, appropriate for a prototype.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _baseUrlController;

  @override
  void initState() {
    super.initState();
    _baseUrlController = TextEditingController(text: context.read<SettingsController>().baseUrl);
  }

  @override
  void dispose() {
    _baseUrlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<SettingsController>();

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Server', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          TextField(
            controller: _baseUrlController,
            decoration: const InputDecoration(
              labelText: 'Server address',
              helperText: 'Android emulator: http://10.0.2.2:8000 · Physical device: your PC\'s LAN IP',
              border: OutlineInputBorder(),
            ),
            keyboardType: TextInputType.url,
            onSubmitted: (value) => settings.setBaseUrl(value.trim()),
            onEditingComplete: () => settings.setBaseUrl(_baseUrlController.text.trim()),
          ),
          const Divider(height: 32),
          Text('Pipeline preset', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          PipelinePresetSelector(
            selected: settings.selectedPreset,
            onSelected: settings.applyPreset,
          ),
          const Divider(height: 32),
          Text('Advanced', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          AdvancedSettingsPanel(
            options: settings.pipelineOptions,
            onChanged: settings.updateOptions,
          ),
          const Divider(height: 32),
          OutlinedButton.icon(
            onPressed: () => context.read<AuthController>().logout(),
            icon: const Icon(Icons.logout),
            label: const Text('Log out'),
          ),
        ],
      ),
    );
  }
}
