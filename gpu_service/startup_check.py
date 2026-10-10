"""Exercise model loading, inference and WAV validation before accepting sessions."""

from pathlib import Path
from tempfile import TemporaryDirectory

from shared.contracts import GenerationRequest, inspect_wav


def verify_generator(generator, wpm_tolerance):
    request = GenerationRequest("startup", "server", "warmup",
                                "The audio service is ready.", 180, 5, sentence_index=1)
    with TemporaryDirectory(prefix="tts-startup-") as directory:
        path = Path(directory) / "warmup.wav"
        generation = generator.generate(request, path)
        details = inspect_wav(path)
        actual_wpm = 60.0 * request.word_count / details["duration_s"]
        if abs(actual_wpm / request.target_wpm - 1) > wpm_tolerance:
            raise ValueError(f"Startup audio WPM {actual_wpm:.2f} exceeds configured tolerance")
        if bool(generation.get("demo_only")) != bool(getattr(generator, "demo_only", False)):
            raise ValueError("Startup audio mode does not match the configured generator")
