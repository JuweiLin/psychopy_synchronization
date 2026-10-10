"""F5-TTS adapter; only the GPU computer needs model dependencies."""

from pathlib import Path
import re

from shared.contracts import sha256_file


def split_article(text, target_wpm, max_seconds=15.0, max_bytes=180):
    """Bound each inference segment; the network still publishes whole articles."""
    word_limit = max(1, int(target_wpm * max_seconds / 60.0))
    chunks, current = [], []
    for token in re.findall(r"\S+\s*", text):
        candidate = "".join(current) + token
        if current and (len(current) >= word_limit or len(candidate.encode("utf-8")) > max_bytes):
            chunks.append("".join(current))
            current = []
        current.append(token)
    if current:
        chunks.append("".join(current))
    return chunks


class F5Generator:
    def __init__(self, ref_audio, ref_text, device="cuda", model="F5TTS_v1_Base", seed=42):
        ref_audio = Path(ref_audio).resolve()
        if not ref_audio.is_file() or not ref_text.strip():
            raise ValueError("Provide an existing reference audio and its transcript")
        self.ref_audio = str(ref_audio)
        self.ref_text = ref_text
        self.device = device
        self.model_name = model
        self.seed = seed
        self._model = None

    def _load(self):
        if self._model is not None:
            return
        from f5_tts.api import F5TTS
        from f5_tts.infer.utils_infer import (
            hop_length, preprocess_ref_audio_text, target_sample_rate,
        )
        import torchaudio

        model = F5TTS(model=self.model_name, device=self.device)
        ref_path, self._ref_text = preprocess_ref_audio_text(self.ref_audio, self.ref_text)
        audio, rate = torchaudio.load(ref_path)
        if rate != target_sample_rate:
            audio = torchaudio.functional.resample(audio, rate, target_sample_rate)
        self._reference = (audio, target_sample_rate)
        # fix_duration includes reference frames; generated audio excludes them.
        self._ref_duration = (audio.shape[-1] // hop_length) * hop_length / target_sample_rate
        self._model = model

    def generate(self, request, output_path):
        self._load()
        import numpy as np
        import soundfile as sf
        from f5_tts.infer.utils_infer import infer_batch_process
        from f5_tts.model.utils import seed_everything

        chunks = split_article(request.text, request.target_wpm)
        waves = []
        for index, chunk in enumerate(chunks):
            seed_everything(self.seed + index)
            chunk_duration = request.target_duration_s * len(chunk.split()) / request.word_count
            # A single explicit batch avoids version-dependent long-text duration
            # allocation. Chunks are concatenated; no time-changing silence removal.
            wav, rate, _ = next(infer_batch_process(
                ref_audio=self._reference,
                ref_text=self._ref_text,
                gen_text_batches=[chunk],
                model_obj=self._model.ema_model,
                vocoder=self._model.vocoder,
                mel_spec_type=self._model.mel_spec_type,
                device=self._model.device,
                progress=None,
                cross_fade_duration=0.0,
                fix_duration=self._ref_duration + chunk_duration,
            ))
            waves.append(wav)
        sf.write(str(output_path), np.concatenate(waves), rate, subtype="PCM_16")
        return {
            "generator": "f5-tts", "model": self.model_name,
            "seed": self.seed, "chunk_count": len(chunks),
            "reference_sha256": sha256_file(self.ref_audio),
            "content_validation": "not_automated",
        }


class DemoGenerator:
    """Silent PCM fixtures for transport checks; never experimental stimuli."""

    demo_only = True

    def generate(self, request, output_path):
        import wave

        rate = 24000
        frames = max(1, round(request.target_duration_s * rate))
        with wave.open(str(output_path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(rate)
            remaining = frames
            while remaining:
                count = min(remaining, 65536)
                audio.writeframesraw(b"\0\0" * count)
                remaining -= count
        return {"generator": "demo-silence", "demo_only": True}
