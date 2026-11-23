#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Install local voice models, validate imports, and create desktop launchers."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import urllib.request
import wave

from core import Config, VOICE, paths


def download_models():
    from faster_whisper.utils import download_model
    model_root = paths()["data"] / "models"
    voices = model_root / "voices"
    voices.mkdir(parents=True, exist_ok=True)
    print("Downloading the British male Piper voice…", flush=True)
    subprocess.run([sys.executable, "-m", "piper.download_voices", "--download-dir", str(voices), VOICE], check=True)
    card = voices / f"{VOICE}-MODEL_CARD.txt"
    if not card.exists():
        try:
            url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/MODEL_CARD"
            with urllib.request.urlopen(url, timeout=30) as response:
                card.write_bytes(response.read())
        except Exception as exc:
            print("Voice attribution is linked in THIRD_PARTY.md. Model card download:", str(exc), flush=True)
    print("Downloading local English speech recognition (base.en)…", flush=True)
    download_model("base.en", output_dir=str(model_root / "whisper-base.en"))
    print("Checking voice synthesis…", flush=True)
    from piper import PiperVoice
    import io
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        PiperVoice.load(str(voices / f"{VOICE}.onnx")).synthesize_wav("Jarvis is ready.", output)
    if len(buffer.getvalue()) < 1000:
        raise RuntimeError("The voice did not produce valid audio.")
    print("Local voice and recognition models are installed.", flush=True)


def launchers(source: Path):
    base = paths()["data"]
    launcher = Path.home() / ".local/bin/jarvis-hybrid"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    python = base / "venv/bin/python"
    state = paths()["state"]
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    launcher.write_text("#!/bin/sh\nset -eu\numask 077\n"
                        f"cd {shlex.quote(str(source))}\n"
                        f"exec {shlex.quote(str(python))} {shlex.quote(str(source / 'app.py'))} "
                        f"2>>{shlex.quote(str(state / 'app.log'))}\n")
    launcher.chmod(0o755)
    icon = base / "jarvis.svg"
    icon.write_text('''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
<rect width="256" height="256" rx="48" fill="#111827"/>
<circle cx="128" cy="128" r="86" fill="none" stroke="#edc473" stroke-width="8"/>
<path d="M151 69v85c0 24-14 37-37 37-17 0-32-9-37-24l21-10c3 9 8 13 16 13 11 0 15-6 15-17V69z" fill="#edc473"/>
</svg>''')
    applications = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    # Desktop entries use their own escaping rules, not shell quoting.
    executable = str(launcher).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
    (applications / "jarvis-hybrid.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Jarvis Hybrid\n"
        "Comment=Local voice and microphone with cloud AI\n"
        f'Exec="{executable}"\nIcon={icon}\nTerminal=false\nCategories=Utility;\nStartupNotify=false\n')
    print("Application launcher created: Jarvis Hybrid", flush=True)
    print("Terminal launcher:", launcher, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--launchers-only", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    if not args.launchers_only:
        import tkinter
        import sounddevice
        import openai
        import faster_whisper
        import piper
        download_models()
    launchers(Path(__file__).resolve().parent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
