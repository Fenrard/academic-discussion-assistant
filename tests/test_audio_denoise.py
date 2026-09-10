"""
clean_audio() — the noise-suppression stage (enable_denoise). Had ZERO
test coverage before this file, which is exactly how it went unnoticed
that the old pyrnnoise/RNNoise implementation had rotted into a hard
runtime failure (pyrnnoise 0.4.3 vs current audiolab/PyAV). It's now
FFmpeg's afftdn filter — no Python dependency, one subprocess call.
"""

import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

from backend.services.audio_service import DENOISE_FILTER, SAMPLE_RATE, clean_audio

_HAS_FFMPEG = shutil.which("ffmpeg") is not None
pytestmark = pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg not on PATH")


def _write_noisy_wav(path, seconds=2.0):
    rng = np.random.default_rng(0)
    samples = int(seconds * SAMPLE_RATE)
    tone = 0.2 * np.sin(2 * np.pi * 220 * np.arange(samples) / SAMPLE_RATE)
    noisy = (tone + rng.normal(0, 0.05, samples)).astype("float32")
    sf.write(path, np.clip(noisy, -1, 1), SAMPLE_RATE, subtype="PCM_16")


def test_disabled_returns_the_input_path_untouched(tmp_path):
    src = tmp_path / "in.wav"
    _write_noisy_wav(src)
    assert clean_audio(src, enable_denoise=False) == src


def test_enabled_produces_a_same_length_16k_mono_wav(tmp_path):
    src = tmp_path / "in.wav"
    _write_noisy_wav(src, seconds=2.0)
    out = clean_audio(src, enable_denoise=True)

    assert out.exists() and out != src
    data, sr = sf.read(out)
    assert sr == SAMPLE_RATE
    assert data.ndim == 1  # mono
    # afftdn is sample-for-sample; allow a few frames of filter delay either way
    assert abs(len(data) - int(2.0 * SAMPLE_RATE)) < SAMPLE_RATE * 0.05


def test_enabled_lowers_the_noise_floor(tmp_path):
    src = tmp_path / "in.wav"
    _write_noisy_wav(src, seconds=3.0)
    before, _ = sf.read(src)
    after, _ = sf.read(clean_audio(src, enable_denoise=True))

    def quietest_rms(x):
        w = SAMPLE_RATE // 5
        return min(np.sqrt(np.mean(x[i:i + w] ** 2)) for i in range(0, len(x) - w, w))

    assert quietest_rms(after) < quietest_rms(before)


def test_filter_string_is_a_valid_ffmpeg_filtergraph():
    # Guards against a typo in DENOISE_FILTER silently turning every
    # denoise-enabled request into a RuntimeError.
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-f", "lavfi", "-i", "anoisesrc=d=0.2:sample_rate=16000",
         "-af", DENOISE_FILTER, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr[-400:]
