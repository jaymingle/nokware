"""Audio for WhatsApp voice notes, through PyAV (FFmpeg bundled in its wheel: nothing to install on the server).

A spoken reply goes as OGG/Opus, the format WhatsApp plays as a voice note (Twilio
accepts OGG only with the Opus codec). If Opus can't be encoded, MP3 is the
fallback: WhatsApp shows it as an audio file rather than a voice note. Incoming
audio is only measured here, or re-encoded when Gemini can't read its format.
"""

import io
import logging
import wave
from dataclasses import dataclass

import av

logger = logging.getLogger(__name__)

SAMPLE_RATE = 48_000
OPUS_BITRATE = 24_000  # plenty for speech
MP3_BITRATE = 48_000


class AudioRejected(ValueError):
    """Not audio that can be read. The text is safe to show the citizen."""


@dataclass(frozen=True)
class Encoded:
    data: bytes
    content_type: str
    extension: str
    seconds: float


FORMATS = (("ogg", "libopus", OPUS_BITRATE, "audio/ogg", "ogg"), ("mp3", "libmp3lame", MP3_BITRATE, "audio/mpeg", "mp3"))


def seconds(data: bytes) -> float:
    """How long a recording is. Raises AudioRejected if it isn't readable audio."""
    try:
        with av.open(io.BytesIO(data)) as container:
            if not container.streams.audio:
                raise AudioRejected("That file has no sound in it.")
            if container.duration:
                return container.duration / av.time_base
            stream = container.streams.audio[0]
            return float(sum(frame.samples for frame in container.decode(stream)) / (stream.rate or SAMPLE_RATE))
    except (av.FFmpegError, OSError, ValueError) as error:
        if isinstance(error, AudioRejected):
            raise
        raise AudioRejected("That voice note couldn't be played.") from None


def wav(pcm: bytes, rate: int) -> bytes:
    """Raw 16-bit mono PCM (what Gemini's speech returns) as a WAV file PyAV can read."""
    out = io.BytesIO()
    with wave.open(out, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(pcm)
    return out.getvalue()


def _encode(source: bytes, container_format: str, codec: str, bitrate: int) -> bytes:
    out = io.BytesIO()
    with av.open(io.BytesIO(source)) as src, av.open(out, "w", format=container_format) as dst:
        stream = dst.add_stream(codec, rate=SAMPLE_RATE, layout="mono")
        stream.bit_rate = bitrate
        sample_format = stream.codec_context.format.name if stream.codec_context.format else "s16"
        resampler = av.AudioResampler(format=sample_format, layout="mono", rate=SAMPLE_RATE)
        for frame in src.decode(audio=0):
            for resampled in resampler.resample(frame):
                dst.mux(stream.encode(resampled))
        for resampled in resampler.resample(None):
            dst.mux(stream.encode(resampled))
        dst.mux(stream.encode(None))
    return out.getvalue()


def voice_note(source: bytes) -> Encoded:
    """Any recording as a WhatsApp voice note: OGG/Opus, or MP3 if Opus fails. Raises AudioRejected."""
    for container_format, codec, bitrate, content_type, extension in FORMATS:
        try:
            data = _encode(source, container_format, codec, bitrate)
        except (av.FFmpegError, OSError, ValueError):
            logger.warning("Couldn't encode a voice note as %s; trying the next format", codec, exc_info=True)
            continue
        return Encoded(data, content_type, extension, seconds(data))
    raise AudioRejected("The recording couldn't be encoded.")
