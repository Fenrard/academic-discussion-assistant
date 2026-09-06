"""
SUPPORTED_EXTENSIONS is intentionally duplicated between
backend/services/audio_service.py and scripts/preprocess_audio.py (the
former is the backend-service promotion of the latter, per CLAUDE.md, and
neither imports the other). Real classroom audio can plausibly arrive from
a basic Android voice-recorder app (.3gp/.amr) or a phone/camera app used
just to capture room sound (.mp4/.mov) -- these were missing from both
copies before this pass and would have made ingest_audio()/preprocess_audio()
reject a file FFmpeg could already decode just fine.
"""

from backend.services.audio_service import SUPPORTED_EXTENSIONS as SERVICE_EXTENSIONS
from scripts.preprocess_audio import SUPPORTED_EXTENSIONS as SCRIPT_EXTENSIONS

_EXPECTED_PHONE_RECORDER_FORMATS = {".3gp", ".3gpp", ".amr", ".mp4", ".mov", ".opus", ".wma"}


def test_both_copies_of_supported_extensions_stay_in_sync():
    assert set(SERVICE_EXTENSIONS) == set(SCRIPT_EXTENSIONS)


def test_common_phone_recorder_formats_are_supported():
    assert _EXPECTED_PHONE_RECORDER_FORMATS.issubset(set(SERVICE_EXTENSIONS))


def test_original_studio_formats_still_supported():
    original = {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac", ".aac"}
    assert original.issubset(set(SERVICE_EXTENSIONS))
