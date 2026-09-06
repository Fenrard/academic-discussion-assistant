import 'dart:convert';
import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show ChangeNotifier, kIsWeb;
import 'package:shared_preferences/shared_preferences.dart';

import '../models/pipeline_config.dart';

/// Non-secret user preferences: server base URL and the current pipeline
/// configuration. Deliberately backed by `shared_preferences`, not
/// `flutter_secure_storage` — nothing here is a credential, and Keystore-
/// backed secure storage is unnecessary overhead for values the user edits
/// freely from the Settings screen. The JWT is the only real secret; see
/// `secure_storage.dart`.
class SettingsController extends ChangeNotifier {
  static const _baseUrlKey = 'server_base_url';
  static const _pipelineOptionsKey = 'pipeline_options_json';
  static const _selectedPresetKey = 'selected_preset';

  final SharedPreferencesAsync _prefs;

  String _baseUrl = _defaultBaseUrl();
  PipelineOptions _pipelineOptions = PipelinePresets.balanced;
  Preset? _selectedPreset = Preset.balanced;
  bool _loaded = false;

  SettingsController({SharedPreferencesAsync? prefs}) : _prefs = prefs ?? SharedPreferencesAsync();

  String get baseUrl => _baseUrl;
  PipelineOptions get pipelineOptions => _pipelineOptions;
  Preset? get selectedPreset => _selectedPreset;
  bool get isLoaded => _loaded;

  /// Android emulator can't reach the host machine via `localhost` — 10.0.2.2
  /// is the documented host-loopback alias for the one AVD available in this
  /// dev environment. A physical device on the same Wi-Fi as the backend
  /// needs the host's real LAN IP instead, hence this being user-editable
  /// rather than hardcoded — see the Settings screen.
  static String _defaultBaseUrl() {
    if (!kIsWeb && Platform.isAndroid) return 'http://10.0.2.2:8000';
    return 'http://127.0.0.1:8000';
  }

  Future<void> load() async {
    final storedBaseUrl = await _prefs.getString(_baseUrlKey);
    if (storedBaseUrl != null && storedBaseUrl.isNotEmpty) {
      _baseUrl = storedBaseUrl;
    }

    final storedOptionsJson = await _prefs.getString(_pipelineOptionsKey);
    if (storedOptionsJson != null) {
      try {
        _pipelineOptions = PipelineOptions.fromJson(jsonDecode(storedOptionsJson) as Map<String, dynamic>);
      } catch (_) {
        // Corrupt/old-shape stored prefs shouldn't crash startup — fall back to Balanced.
        _pipelineOptions = PipelinePresets.balanced;
      }
    }

    final storedPreset = await _prefs.getString(_selectedPresetKey);
    _selectedPreset = switch (storedPreset) {
      'fast' => Preset.fast,
      'balanced' => Preset.balanced,
      'accurate' => Preset.accurate,
      'custom' => null,
      _ => PipelinePresets.matching(_pipelineOptions),
    };

    _loaded = true;
    notifyListeners();
  }

  Future<void> setBaseUrl(String url) async {
    _baseUrl = url;
    notifyListeners();
    await _prefs.setString(_baseUrlKey, url);
  }

  Future<void> applyPreset(Preset preset) async {
    _pipelineOptions = PipelinePresets.resolve(preset);
    _selectedPreset = preset;
    notifyListeners();
    await _persistPipelineOptions();
  }

  /// Any manual edit from the advanced panel clears the selected preset to
  /// "Custom" — presets are just three named starting points, not a
  /// maintained mode (see the build plan's pipeline_config design notes).
  Future<void> updateOptions(PipelineOptions options) async {
    _pipelineOptions = options;
    _selectedPreset = PipelinePresets.matching(options);
    notifyListeners();
    await _persistPipelineOptions();
  }

  Future<void> _persistPipelineOptions() async {
    await _prefs.setString(_pipelineOptionsKey, jsonEncode(_pipelineOptions.toJson()));
    await _prefs.setString(_selectedPresetKey, _selectedPreset?.name ?? 'custom');
  }
}
