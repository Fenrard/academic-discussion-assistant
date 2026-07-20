from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

SAMPLE_RATE = 16000
CHANNELS = 1
DURATION_SECONDS = 3
OUTPUT_FILENAME = "classroom.wav"


def record_audio(duration_seconds: int, sample_rate: int, channels: int) -> np.ndarray:
    frame_count = duration_seconds * sample_rate

    print(f"Recording for {duration_seconds} seconds...")

    audio_buffer = sd.rec(
        frames=frame_count,
        samplerate=sample_rate,
        channels=channels,
        dtype="int16",
    )

    sd.wait()

    print("Recording finished.")

    return audio_buffer


def save_recording(audio_data: np.ndarray, sample_rate: int, filename: str) -> Path:
    output_path = Path(__file__).resolve().parent.parent / "recordings" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sf.write(output_path, audio_data, samplerate=sample_rate)

    print(f"Saved recording to: {output_path}")

    return output_path


def inspect_wav_file(file_path: Path) -> None:
    info = sf.info(file_path)

    print(f"Channels: {info.channels}")
    print(f"Sample rate: {info.samplerate} Hz")
    print(f"Bit depth: {info.subtype_info}")
    print(f"Duration: {info.duration:.2f} seconds")

def main() -> None:
    try:
        audio_data = record_audio(
            duration_seconds=DURATION_SECONDS,
            sample_rate=SAMPLE_RATE,
            channels=CHANNELS,
        )
    except sd.PortAudioError as error:
        print(f"Could not access the microphone: {error}")
        return

    output_path = save_recording(
        audio_data=audio_data,
        sample_rate=SAMPLE_RATE,
        filename=OUTPUT_FILENAME,
    )

    inspect_wav_file(output_path)
    
if __name__ == "__main__":
    main()