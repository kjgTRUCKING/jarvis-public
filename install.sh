#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -Eeuo pipefail
umask 077

if [ "${EUID:-$(id -u)}" -eq 0 ]; then
    printf 'Run this installer as your normal Ubuntu user, without sudo.\n'
    exit 1
fi
if ! command -v apt-get >/dev/null; then
    printf 'This installer is for Ubuntu or Debian Linux.\n'
    exit 1
fi

source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
jarvis_data="${XDG_DATA_HOME:-$HOME/.local/share}/jarvis-hybrid"
jarvis_state="${XDG_STATE_HOME:-$HOME/.local/state}/jarvis-hybrid"
mkdir -p "$jarvis_state" "$jarvis_data/releases"
exec > >(tee -a "$jarvis_state/install.log") 2>&1
trap 'printf "\nInstallation stopped at line %s. The last error is above.\nLog: %s/install.log\n" "$LINENO" "$jarvis_state"' ERR

printf '\nInstalling Jarvis Hybrid for %s\n' "$(id -un)"
printf 'Local microphone + British male voice + cloud AI\n\n'
printf 'Ubuntu may ask for your password to install Python and audio support.\n'
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-tk libportaudio2 xdg-utils

/usr/bin/python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit('Python 3.12 or newer is required. Use Ubuntu 24.04 or newer.')
PY

if [ ! -x "$jarvis_data/venv/bin/python" ]; then
    /usr/bin/python3 -m venv "$jarvis_data/venv"
fi
printf '\nInstalling isolated Python dependencies…\n'
"$jarvis_data/venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip
"$jarvis_data/venv/bin/python" -m pip install --disable-pip-version-check -r "$source_dir/requirements.txt"

release_dir="$jarvis_data/releases/2026.11.21.1-$(date +%Y%m%d%H%M%S)-$$"
mkdir -p "$release_dir"
cp -R "$source_dir"/. "$release_dir"/
printf '\nInstalling local voice and speech recognition. Downloads may take a few minutes.\n'
"$jarvis_data/venv/bin/python" "$release_dir/bootstrap.py"

# Update the installed application only after dependencies and models succeed.
if [ -e "$jarvis_data/current" ] && [ ! -L "$jarvis_data/current" ]; then
    printf 'The path %s/current already exists and is not a managed symlink.\n' "$jarvis_data"
    exit 1
fi
ln -s "$release_dir" "$jarvis_data/current.next-$$"
mv -Tf "$jarvis_data/current.next-$$" "$jarvis_data/current"

printf '\nJarvis Hybrid is installed.\n'
printf 'Find “Jarvis Hybrid” in Ubuntu Applications.\n'
printf 'Enter your OpenAI API key inside Settings, then click Talk.\n'
printf 'A startup voice announcement will play through your selected speaker.\n'
if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    "$HOME/.local/bin/jarvis-hybrid" >"$jarvis_state/launch.log" 2>&1 &
    jarvis_pid=$!
    sleep 1
    if ! kill -0 "$jarvis_pid" 2>/dev/null; then
        printf '\nThe application closed during startup. Details:\n'
        tail -25 "$jarvis_state/app.log" "$jarvis_state/launch.log" 2>/dev/null || true
        exit 1
    fi
else
    printf '\nOpen a desktop session and run: %s/.local/bin/jarvis-hybrid\n' "$HOME"
fi
