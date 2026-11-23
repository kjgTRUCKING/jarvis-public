# Jarvis Hybrid for Ubuntu

A standalone desktop assistant for Ubuntu. It uses local speech recognition and a
local British male Piper voice, with an OpenAI cloud model for reasoning. It opens
its own application window. No browser is needed to use the assistant.

## Install

Clone or download this repository. In an Ubuntu terminal, open its folder and run:

```bash
bash install.sh
```

Run as your ordinary user, without putting `sudo` before the installer command. The
installer asks Ubuntu to install Python, Tk and audio support using `sudo`, then
keeps the application and Python packages under your own account. It downloads
the voice and speech recognition models. Allow several hundred MB of downloads
and about 1 GB of available storage. Downloads require internet access.

Ubuntu 24.04 or newer with Python 3.12 or newer, x86-64, is the intended platform. The dependency wheels
also exist for other Linux platforms, but those configurations were not tested.

## Start

Search Ubuntu Applications for **Jarvis Hybrid**. To personalize greetings and your chat label, enter **Your name (optional)**
in Settings. The app saves the name locally. You can clear it or turn off the
startup greeting at any time.

1. Click **Test voice**. It works without an API key.
2. Open **Settings**, enter your OpenAI API key, and save.
3. Type a message and press Enter, or click **Talk**, speak, then click
   **Finish speaking**. A recording stops automatically after 90 seconds.
4. Jarvis recognizes your speech locally, sends the text to the cloud model,
   displays the answer, and speaks it through Piper.

Shift+Enter adds a line. **Stop** stops recording/speech and prevents further
tool execution for the current request. A cloud request already sent may take
up to its 60-second timeout to return. **Save chat** exports the visible chat.

Create a key at https://platform.openai.com/api-keys. API access uses the credits
and billing of your OpenAI API account. This app does not sign in with your
ChatGPT subscription or inherit ChatGPT history, memory, plugins or connections.
It never needs you to paste an API key into a ChatGPT conversation.

The default model is `gpt-6.2-sol`; you can choose another available model or
type its API ID in Settings. Model availability depends on your API account.

## Local tools

Tools can read system information, list/read/write text files in the selected
working folder, open common Ubuntu apps, open requested web URLs, and run shell
commands. Existing files written by the file tool get backups. Choose the project folder you want to work in under Settings.

Terminal commands show the exact command and working folder before execution
by default. You can change that preference in Settings. Commands run as your
normal Linux user; the application does not grant root access. Administrator
commands must be run in your own terminal. Commands have a 45-second timeout,
no interactive standard input, and limited returned output.

The working folder constrains the file tools and command starting directory;
it is not an operating-system sandbox. An approved shell command runs with
your normal Linux account's access. The app removes common secret variables
from child environments, masks known API keys, and excludes common credential
paths from its file tools. These measures are not a sandbox for arbitrary shell
code. Use the command review window to inspect what will run.

Opening a browser page does not give Jarvis its contents. This version does not
include web search, screen clicking, a wake word, Claude/Grok connections, or an
offline reasoning model. Microphone access begins when you click Talk; the
application does not listen continuously. You can disable local computer tools
and use conversation alone.

## Privacy and files

Raw microphone recordings are held in memory and transcribed on your PC. The
app sends recognized or typed text and relevant tool results to the OpenAI API.
Piper synthesizes spoken replies locally. The models need no cloud audio
service after installation. Cloud reasoning still needs internet access.

The API key is in `~/.config/jarvis-hybrid/credentials.json`, a private file
(mode 600) inside a private folder (mode 700). It is not encrypted on disk.
An `OPENAI_API_KEY` environment variable can also supply a key if none is saved.

Settings: `~/.config/jarvis-hybrid/`

Application and models: `~/.local/share/jarvis-hybrid/`

Conversation transcripts, file backups and logs: `~/.local/state/jarvis-hybrid/`

The app uses XDG directories if you have customized them. Conversation files
contain visible messages, not hidden model reasoning. A new app session starts
a fresh cloud conversation. Saved transcripts are available as local JSON files
or through Save chat; this version does not restore model conversation state.

## Troubleshooting

- No sound: select the speaker in Settings and check Ubuntu Sound output.
- No microphone: select the microphone in Settings and check Ubuntu Sound input.
- Voice missing or installation interrupted: run the installer again. It keeps
  your settings and conversations.
- Invalid key, quota or unavailable model: the app displays a specific message.
  Check your API account and the selected model.
- Use `~/.local/bin/jarvis-hybrid` to launch from a terminal.
- Installation log: `~/.local/state/jarvis-hybrid/install.log`.
- Application log: `~/.local/state/jarvis-hybrid/app.log`.

## Validation

See `VALIDATION.md` for the checks performed on this build and their limits.

Version 2026.11.21.1. This project is
licensed GPL-3.0-or-later. Dependencies and voice models have their own licenses;
see THIRD_PARTY.md and LICENSE.

## Contributing

Anyone can propose edits through a fork and pull request. See [CONTRIBUTING.md](CONTRIBUTING.md). Local computer tools are off by default in a fresh configuration.
