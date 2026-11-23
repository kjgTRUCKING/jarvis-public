# SPDX-License-Identifier: GPL-3.0-or-later
"""Local-only speech input and Piper speech output; no cloud audio upload."""
from __future__ import annotations

import io
from pathlib import Path
import threading
import time
import wave

from core import Config, paths
from jarvis_speech_text import speech_text


class Audio:
    def __init__(self, config: Config):
        self.config = config
        self._voice = None
        self._recognizer = None
        self._speak_lock = threading.Lock()
        self._cancel_speech = threading.Event()
        self._record_stop = threading.Event()
        self._record_cancel = threading.Event()
        self._recording = threading.Event()

    @staticmethod
    def devices():
        import sounddevice as sd
        return [dict(item, index=index) for index, item in enumerate(sd.query_devices())]

    def stop_speech(self):
        self._cancel_speech.set()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    def speak(self, text: str):
        # Queue ownership is managed by the UI; no parallel speech workers.
        with self._speak_lock:
            self._cancel_speech.clear()
            import numpy as np
            import sounddevice as sd
            from piper import PiperVoice
            model = paths()["data"] / "models/voices" / f"{self.config.voice}.onnx"
            if not model.is_file():
                raise RuntimeError("The Piper voice is missing. Run the installer again to download it.")
            if self._voice is None:
                self._voice = PiperVoice.load(str(model))
            readable = speech_text(text)[:2200]
            if not readable:
                return
            for chunk in self._voice.synthesize(readable):
                if self._cancel_speech.is_set():
                    break
                samples = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                sd.play(samples, samplerate=chunk.sample_rate, device=self.config.speaker)
                sd.wait()

    def end_recording(self):
        self._record_stop.set()

    def cancel_recording(self):
        self._record_cancel.set()
        self._record_stop.set()

    def prepare_recording(self):
        self._record_stop.clear()
        self._record_cancel.clear()

    def record(self, status):
        import numpy as np
        import sounddevice as sd
        self._recording.set()
        blocks = []
        errors = []
        device = sd.query_devices(self.config.microphone, "input")
        rate = int(device["default_samplerate"])
        # Use the microphone's native rate; some USB devices reject 16 kHz.
        max_frames = rate * 90
        frames = 0

        def callback(data, count, timing, flags):
            nonlocal frames
            if flags:
                errors.append(str(flags))
            if frames < max_frames:
                blocks.append(data.copy())
                frames += count
            else:
                self._record_stop.set()

        try:
            with sd.InputStream(samplerate=rate, channels=1, dtype="int16", device=self.config.microphone,
                                callback=callback):
                status("Listening — click Finish speaking when you're done.")
                self._record_stop.wait(90)
            if self._record_cancel.is_set():
                return None
            if not blocks:
                raise RuntimeError("No microphone audio was captured. Check the microphone in Settings.")
            samples = np.concatenate(blocks, axis=0)
            if np.max(np.abs(samples.astype(np.int32))) < 100:
                raise RuntimeError("The microphone was nearly silent. Check mute, input volume and device selection.")
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(rate)
                stream.writeframes(samples.tobytes())
            buffer.seek(0)
            return buffer
        finally:
            self._recording.clear()

    def transcribe(self, source):
        from faster_whisper import WhisperModel
        model_dir = paths()["data"] / "models" / f"whisper-{self.config.whisper}"
        if not model_dir.is_dir():
            raise RuntimeError("The local speech recognition model is missing. Run the installer again.")
        if self._recognizer is None:
            self._recognizer = WhisperModel(str(model_dir), device="cpu", compute_type="int8", cpu_threads=4)
        segments, _ = self._recognizer.transcribe(source, language="en", vad_filter=True, beam_size=3,
                                                  condition_on_previous_text=False)
        result = " ".join(segment.text.strip() for segment in segments).strip()
        if not result:
            raise RuntimeError("I didn't catch speech. Try again a little closer to the microphone.")
        return result
