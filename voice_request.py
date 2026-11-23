"""Answer one transcribed wake request with the Jarvis Hybrid cloud backend."""

import sys
from threading import Event

from core import Brain, Config


def main():
    try:
        question = sys.stdin.read().strip()
        if not question:
            return 2
        reply = Brain(Config.load(), lambda *_: False).ask(question, Event(), voice=True)
    except Exception as exc:
        print(f"Jarvis Hybrid voice request failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
