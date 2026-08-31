"""
Temp-file helpers shared by the POST upload path and the WebSocket
streaming path. process_pipeline()-derived logic expects a Path on disk
(same handoff shape the scripts already use), so both entry points funnel
raw bytes through here before touching backend/services/audio_service.py.
"""

import tempfile
import uuid
from pathlib import Path

_TEMP_DIR = Path(tempfile.gettempdir()) / "scaitale"
_TEMP_DIR.mkdir(parents=True, exist_ok=True)


def write_temp_audio(data: bytes, suffix: str = ".wav") -> Path:
    """Writes raw audio bytes to a uniquely-named temp file, returns its path."""
    temp_path = _TEMP_DIR / f"{uuid.uuid4().hex}{suffix}"
    temp_path.write_bytes(data)
    return temp_path


def cleanup_temp_files(*paths: Path) -> None:
    """Best-effort cleanup — never lets a missing/locked file raise."""
    for path in paths:
        try:
            if path and path.exists():
                path.unlink()
        except OSError:
            pass
