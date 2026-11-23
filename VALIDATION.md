# Build validation — 2026-11-21

Completed in a Debian 13 x86-64 workspace using Python 3.12:

- 15 automated tests passed. These cover file backups and permissions,
  path/symlink constraints, declined commands, command cancellation, output
  limits, API key masking, local recording sample rates, and canceled recording.
- The real OpenAI Python SDK was tested with an HTTP mock transport: a tool
  call executed locally, its result returned to the next Responses request,
  conversation history and encrypted reasoning context carried forward,
  authentication failure did not commit partial history, and cancellation
  prevented tool execution after a response. No paid cloud inference was used.
- The real Alan Piper model generated 5.89 seconds of speech. The real local
  base.en recognizer transcribed the spoken greeting and a request to open the
  calculator.
- A PyAV 19 incompatibility with faster-whisper was found and corrected by
  pinning PyAV 16.0.1. The synthesis/transcription test passed after the change.
- The installation workflow completed in an isolated XDG destination whose
  path included spaces, using the real dependencies, model setup, synthesis
  check, release activation and launcher creation. The sudo/apt system package
  step was simulated; no Ubuntu system packages were changed by that test.
- Python source compilation and shell syntax checks passed.
- The self-extracting installer was checked for extraction integrity, source
  completeness, operation from a path containing spaces, and rejection of a
  tampered payload.

Limits: the native desktop window could not be visually exercised in this
workspace. Physical microphone capture, speaker playback, a live OpenAI API
request, and installation with the real Ubuntu package manager must be checked
on the target Ubuntu PC. Start with Test voice, then a typed cloud request,
then Talk. Test recordings used simulated microphone input; the speech-model
round trip used real generated audio.

Run the included tests after installation:

```bash
cd ~/.local/share/jarvis-hybrid/current
~/.local/share/jarvis-hybrid/venv/bin/python -m unittest discover -s tests -v
```
