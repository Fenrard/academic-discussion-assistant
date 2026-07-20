import argparse
import sys
import shutil
import subprocess
import json

from pathlib import Path

SUPPORTED_EXTENSIONS = (".wav", ".mp3", ".m4a",".ogg",".webm",".flac",".aac")
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
DEFAULT_OUTPUT_FILENAME = "lecture_preprocessed.wav"


def check_dependencies() -> None:
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            raise EnvironmentError(
                f"'{binary}' not found on PATH. Install FFmpeg and confirm "
                f"both 'ffmpeg' and 'ffprobe' run from your terminal."
            )


def validate_input_file(input_path: Path) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"No file found at: {input_path}")

    if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{input_path.suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    

def inspect_audio(input_path: Path) -> dict:
   
    command = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(input_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on '{input_path.name}': {result.stderr.strip()}")

    probe_data = json.loads(result.stdout)
    audio_stream = next(
        (s for s in probe_data.get("streams", []) if s.get("codec_type") == "audio"),
        None,
    )
    if audio_stream is None:
        raise ValueError(f"No audio stream found in '{input_path.name}'.")

    return {
        "filename": input_path.name,
        "codec": audio_stream.get("codec_name", "unknown"),
        "duration_seconds": float(probe_data["format"].get("duration", 0.0)),
        "sample_rate": int(audio_stream.get("sample_rate", 0)),
        "channels": audio_stream.get("channels", "unknown"),
        "bitrate": probe_data["format"].get("bit_rate", "unknown"),
    }

def print_metadata(metadata: dict) -> None:
    print("Input file metadata:")
    print(f"  Filename:    {metadata['filename']}")
    print(f"  Codec:       {metadata['codec']}")
    print(f"  Duration:    {metadata['duration_seconds']:.2f} seconds")
    print(f"  Sample rate: {metadata['sample_rate']} Hz")
    print(f"  Channels:    {metadata['channels']}")
    print(f"  Bitrate:     {metadata['bitrate']}")


def preprocess_audio(input_path: Path, output_path: Path) -> Path:
    
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", str(TARGET_CHANNELS),
        "-c:a", "pcm_s16le",
        "-af", "loudnorm",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on '{input_path.name}': {result.stderr.strip()}")

    return output_path


def main() -> None:

    parser = argparse.ArgumentParser(description="Standardize audio for Whisper.")
    parser.add_argument("input_file", type=str, help="Path to the input audio file.")
    args = parser.parse_args()

    input_path = Path(args.input_file).resolve()
    output_path = Path(__file__).resolve().parent.parent / "recordings" / DEFAULT_OUTPUT_FILENAME

    try:
        check_dependencies()
        validate_input_file(input_path)
        metadata = inspect_audio(input_path)
        print_metadata(metadata)
        preprocess_audio(input_path, output_path)
    except (EnvironmentError, FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    print(f"\nPreprocessing complete. Saved to: {output_path}")

if __name__ == "__main__":
    main()












