"""
_suffix_from_filename() -- pure logic factored out of POST /transcribe so it
can be tested without spinning up the endpoint (auth, DB, Celery task
enqueueing). Determines what extension an uploaded file's temp copy gets
saved under, which in turn decides whether ingest_audio()'s
SUPPORTED_EXTENSIONS gate even gives the upload a chance.
"""

from backend.api.transcribe import _suffix_from_filename


def test_normal_extension_is_preserved():
    assert _suffix_from_filename("classroom.m4a") == ".m4a"


def test_last_dot_wins_for_a_dotted_filename():
    assert _suffix_from_filename("classroom recording 09.07.2026.wav") == ".wav"


def test_no_filename_falls_back_to_wav():
    assert _suffix_from_filename(None) == ".wav"


def test_no_extension_falls_back_to_wav():
    assert _suffix_from_filename("classroom") == ".wav"


def test_trailing_dot_falls_back_to_wav_instead_of_a_bare_dot():
    # Regression test: "classroom." has "." in it, so the old
    # `"." + filename.rsplit(".", 1)[-1]` produced a suffix of "." (an
    # empty extension) -- not in SUPPORTED_EXTENSIONS, so an otherwise
    # perfectly valid upload was rejected with a confusing
    # "Unsupported file type ''" before ingest_audio() ever ran FFmpeg on it.
    assert _suffix_from_filename("classroom.") == ".wav"
