"""
Clean error handling for FastAPI routes — the same pattern CLAUDE.md
calls out from record_test_audio.py's sd.PortAudioError handling
("clean message, not raw traceback"), generalized to every pipeline
stage's expected exception types.
"""

from fastapi import HTTPException

# The exception types every promoted script function is documented to
# raise on bad input/environment — never a bare Exception.
PIPELINE_ERRORS = (FileNotFoundError, ValueError, RuntimeError, EnvironmentError)


def as_http_exception(error: Exception, status_code: int = 400) -> HTTPException:
    """Maps a known pipeline error to a clean HTTPException; anything else stays a 500."""
    if isinstance(error, PIPELINE_ERRORS):
        return HTTPException(status_code=status_code, detail=str(error))
    return HTTPException(status_code=500, detail=f"Unexpected server error: {error}")
