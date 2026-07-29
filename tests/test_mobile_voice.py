"""Tests for mobile voice audio helpers."""

import io
import wave

import numpy as np

from core.mobile_voice import decode_wav_to_float32


def _wav_bytes(samples: np.ndarray, sample_rate: int = 16000) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


class TestMobileVoice:
    def test_decodes_wav_to_float32(self):
        audio = _wav_bytes(np.array([0.0, 0.5, -0.5], dtype=np.float32))

        samples, sample_rate = decode_wav_to_float32(audio)

        assert sample_rate == 16000
        assert samples.dtype == np.float32
        assert samples[0] == 0.0
        assert samples[1] > 0.49
        assert samples[2] < -0.49
