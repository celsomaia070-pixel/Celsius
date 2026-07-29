"""Local mobile voice transcription helpers."""

import io
import wave

import numpy as np

_mobile_whisper_model = None


def decode_wav_to_float32(audio: bytes) -> tuple[np.ndarray, int]:
    """Decode PCM WAV bytes into mono float32 samples."""

    with wave.open(io.BytesIO(audio), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())

    if not frames:
        raise ValueError("Audio vazio.")

    if sample_width == 1:
        samples = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sample_width == 2:
        samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 4:
        samples = np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"WAV com profundidade de {sample_width * 8} bits nao suportada.")

    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)

    return samples.astype(np.float32), sample_rate


def transcribe_mobile_wav(audio: bytes, *, model_name: str = "small") -> str:
    """Transcribe browser-recorded WAV without requiring external ffmpeg."""

    global _mobile_whisper_model

    samples, sample_rate = decode_wav_to_float32(audio)
    if len(samples) < sample_rate * 0.3:
        raise ValueError("Audio muito curto. Fale por mais tempo.")
    if float(np.max(np.abs(samples))) < 0.003:
        raise ValueError("Audio muito silencioso. Fale mais perto do celular.")

    if sample_rate != 16000:
        samples = _resample_linear(samples, sample_rate, 16000)

    if _mobile_whisper_model is None:
        try:
            from faster_whisper import WhisperModel
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "faster-whisper nao esta instalado para transcrever voz local."
            ) from exc

        _mobile_whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")

    segments, _info = _mobile_whisper_model.transcribe(
        samples,
        language="pt",
        beam_size=3,
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": 300,
            "speech_pad_ms": 200,
        },
        initial_prompt="Portugues do Brasil. Comando curto para o Celsius Project AI.",
        word_timestamps=False,
    )
    transcript = " ".join(segment.text.strip() for segment in segments).strip()
    if not transcript:
        raise ValueError("Nao consegui entender a gravacao.")
    return transcript


def _resample_linear(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return samples.astype(np.float32)
    duration = len(samples) / float(source_rate)
    target_length = max(1, int(duration * target_rate))
    source_positions = np.linspace(0.0, len(samples) - 1, num=len(samples), dtype=np.float32)
    target_positions = np.linspace(0.0, len(samples) - 1, num=target_length, dtype=np.float32)
    return np.interp(target_positions, source_positions, samples).astype(np.float32)
