"""Article requests and WAV inspection shared by both computers."""

from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
from typing import Optional
import wave


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_wav(path):
    """Check PCM WAV readability and ensure the declared frames really exist."""
    with wave.open(str(path), "rb") as audio:
        frames = audio.getnframes()
        rate = audio.getframerate()
        bytes_per_frame = audio.getnchannels() * audio.getsampwidth()
        if frames <= 0 or rate <= 0 or bytes_per_frame <= 0:
            raise ValueError("WAV must contain audio frames")
        remaining = frames
        while remaining:
            count = min(remaining, 65536)
            if len(audio.readframes(count)) != count * bytes_per_frame:
                raise ValueError("WAV data is truncated")
            remaining -= count
        return {"duration_s": frames / rate, "sample_rate_hz": rate}


@dataclass(frozen=True)
class GenerationRequest:
    session_id: str
    participant_id: str
    article_id: str
    text: str
    target_wpm: float
    word_count: int
    sentence_index: Optional[int] = None

    def __post_init__(self):
        for name in ("session_id", "participant_id", "article_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise ValueError(f"{name} must be a nonempty string of at most 128 characters")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must be a nonempty string")
        if isinstance(self.target_wpm, bool) or not isinstance(self.target_wpm, (int, float)):
            raise ValueError("target_wpm must be numeric")
        if not math.isfinite(self.target_wpm) or self.target_wpm <= 0:
            raise ValueError("target_wpm must be finite and positive")
        if type(self.word_count) is not int or self.word_count <= 0:
            raise ValueError("word_count must be a positive integer")
        if self.word_count != len(self.text.split()):
            raise ValueError("word_count must match whitespace-separated tokens in text")
        if self.sentence_index is not None and (type(self.sentence_index) is not int or self.sentence_index < 1):
            raise ValueError("sentence_index must be a positive integer")
        if not math.isfinite(self.target_duration_s):
            raise ValueError("Target duration is not finite")

    @property
    def target_duration_s(self):
        return 60.0 * self.word_count / self.target_wpm

    @property
    def text_sha256(self):
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def to_dict(self):
        return asdict(self)

    def identity(self):
        identity = {
            "session_id": self.session_id,
            "participant_id": self.participant_id,
            "article_id": self.article_id,
            "text_sha256": self.text_sha256,
            "word_count": self.word_count,
            "target_wpm": self.target_wpm,
            "target_duration_s": self.target_duration_s,
        }
        if self.sentence_index is not None:
            identity["sentence_index"] = self.sentence_index
        return identity

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Each article must be an object")
        try:
            return cls(
                session_id=data["session_id"],
                participant_id=data["participant_id"],
                article_id=data["article_id"],
                text=data["text"],
                target_wpm=data["target_wpm"],
                word_count=data["word_count"],
                sentence_index=data.get("sentence_index"),
            )
        except KeyError as exc:
            raise ValueError(f"Missing article field: {exc.args[0]}") from exc
