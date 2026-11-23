"""Turn formatted Jarvis replies into text for the speech synthesizer."""

import html
import re
import unicodedata


def speech_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"(?ms)^\s*(?:```|~~~)[^\n]*\n.*?(?:^\s*(?:```|~~~)[^\n]*$|\Z)", " ", text)
    text = re.sub(r"!?\[([^\]\n]+)\]\([^\n)]+\)", r"\1", text)
    text = re.sub(r"https?://[^\s<>]+", " ", text)
    text = re.sub(r"(?m)^\s*(?:[-+*•]|\d+[.)])\s+", "", text)
    text = re.sub(r"(?m)^\s*(?:[-*_]\s*){3,}$", "", text)
    text = re.sub(r"[#*`>|~]", "", text)
    text = re.sub(r"_+", " ", text)
    text = re.sub(r"[\u200d\ufe0e\ufe0f\u20e3]", "", text)
    text = "".join(
        " " if unicodedata.category(char) in {"So", "Sk"} else char
        for char in text
    )
    return " ".join(text.split())
