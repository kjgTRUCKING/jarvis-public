# SPDX-License-Identifier: GPL-3.0-or-later
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_local import Audio, speech_text
from core import Config


class AudioTests(unittest.TestCase):
    def test_speech_excludes_code_and_link_syntax(self):
        text = speech_text("**Hello** [Alex](https://example.com).\n```bash\nsudo example\n``` https://example.com")
        self.assertIn("Hello Alex", text)
        self.assertNotIn("sudo", text)
        self.assertNotIn("https://", text)

    def test_recording_preserves_microphone_native_sample_rate(self):
        import numpy as np
        import sounddevice as sd
        audio = Audio(Config())
        audio.prepare_recording()
        class Stream:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
            def __enter__(self):
                self.kwargs["callback"](np.full((4800, 1), 1200, dtype=np.int16), 4800, None, None)
                audio.end_recording()
            def __exit__(self, *_):
                pass
        with patch.object(sd, "query_devices", return_value={"default_samplerate": 48000}), patch.object(sd, "InputStream", Stream):
            source = audio.record(lambda *_: None)
        with wave.open(source, "rb") as wav:
            self.assertEqual(wav.getframerate(), 48000)
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getnframes(), 4800)

    def test_canceled_recording_is_not_transcribed(self):
        import sounddevice as sd
        audio = Audio(Config())
        audio.prepare_recording()
        class Stream:
            def __init__(self, **kwargs):
                pass
            def __enter__(self):
                audio.cancel_recording()
            def __exit__(self, *_):
                pass
        with patch.object(sd, "query_devices", return_value={"default_samplerate": 48000}), patch.object(sd, "InputStream", Stream):
            self.assertIsNone(audio.record(lambda *_: None))


if __name__ == "__main__":
    unittest.main()
