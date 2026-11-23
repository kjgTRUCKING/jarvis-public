#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone Tk desktop application. All Tk calls run on the main thread."""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from audio_local import Audio
from core import (
    Brain, Cancelled, Config, VERSION, atomic_json, friendly_error, open_in_firefox,
    paths, redact, without_citations,
)

BG, PANEL, TEXT, MUTED, GOLD = "#111827", "#1c2638", "#eef2f8", "#a6b4c9", "#edc473"


class App:
    def __init__(self, root: tk.Tk, config=None):
        self.root = root
        self.config = config or Config.load()
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.audio = Audio(self.config)
        self.brain = Brain(self.config, self.approve, self.emit)
        self.busy = False
        self.job_kind = ""
        self.closed = False
        self.messages = []
        self.last_answer = ""
        self.worker = None
        self.record_finishing = False
        self.review_windows = []
        self.session_path = paths()["state"] / "conversations" / (dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
        self._draw()
        self.add("Jarvis", self.greeting("Hello") + " Your voice and microphone work locally; the cloud handles reasoning.\n"
                 "Start with Test voice, then open Settings to connect your API key.\n"
                 "Click Talk, speak, then click Finish speaking to send your request.")
        self.set_status("Ready" if self.config.api_key else "Voice ready • Cloud key needed in Settings")
        self.root.after(60, self.poll)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if self.config.startup_announcement:
            self.root.after(700, lambda: self.speak(self.greeting("Jarvis is ready")))

    def _draw(self):
        root = self.root
        root.title("Jarvis Hybrid")
        root.configure(bg=BG)
        root.geometry("1000x740")
        root.minsize(760, 580)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("DejaVu Sans", 11))
        style.configure("TButton", font=("DejaVu Sans", 11), padding=(12, 9), background=PANEL, foreground=TEXT)
        style.map("TButton", background=[("active", "#34435b")], foreground=[("disabled", "#6b778b")])
        style.configure("Gold.TButton", background=GOLD, foreground=BG, font=("DejaVu Sans", 11, "bold"))
        style.map("Gold.TButton", background=[("active", "#ffdda0")])
        style.configure("TCheckbutton", background=BG, foreground=TEXT, font=("DejaVu Sans", 10))
        top = ttk.Frame(root, padding=(24, 18))
        top.pack(fill="x")
        tk.Label(top, text="JARVIS", bg=BG, fg=GOLD, font=("DejaVu Sans", 25, "bold")).pack(side="left")
        tk.Label(top, text="  Local voice · Cloud reasoning", bg=BG, fg=MUTED,
                 font=("DejaVu Sans", 11)).pack(side="left", padx=12)
        self.settings_button = ttk.Button(top, text="Settings", command=self.settings)
        self.settings_button.pack(side="right")
        self.chat = scrolledtext.ScrolledText(root, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                      font=("DejaVu Sans", 12), wrap="word", relief="flat", padx=20, pady=16, state="disabled")
        self.chat.pack(fill="both", expand=True, padx=24)
        self.chat.tag_config("User", foreground="#83c5ff", font=("DejaVu Sans", 11, "bold"))
        self.chat.tag_config("Jarvis", foreground=GOLD, font=("DejaVu Sans", 11, "bold"))
        self.chat.tag_config("System", foreground=MUTED, font=("DejaVu Sans", 10, "italic"))
        self.chat.tag_config("Tool", foreground="#b1c2db", font=("DejaVu Sans Mono", 9))
        entry_frame = ttk.Frame(root, padding=(24, 14, 24, 0))
        entry_frame.pack(fill="x")
        self.entry = tk.Text(entry_frame, height=3, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                            font=("DejaVu Sans", 12), wrap="word", relief="flat", padx=12, pady=10)
        self.entry.pack(fill="x")
        self.entry.bind("<Return>", self.enter)
        buttons = ttk.Frame(root, padding=(24, 10, 24, 10))
        buttons.pack(fill="x")
        self.talk_button = ttk.Button(buttons, text="Talk", style="Gold.TButton", command=self.talk)
        self.talk_button.pack(side="left")
        self.send_button = ttk.Button(buttons, text="Send", command=self.send)
        self.send_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")
        self.voice_button = ttk.Button(buttons, text="Test voice", command=lambda: self.speak(self.greeting("Jarvis is ready") + " Your local voice is working."))
        self.voice_button.pack(side="left", padx=8)
        self.new_button = ttk.Button(buttons, text="New conversation", command=self.new_chat)
        self.new_button.pack(side="right")
        self.export_button = ttk.Button(buttons, text="Save chat", command=self.export)
        self.export_button.pack(side="right", padx=8)
        self.status_var = tk.StringVar()
        tk.Label(root, textvariable=self.status_var, bg=BG, fg=MUTED, anchor="w",
                 font=("DejaVu Sans", 10), padx=24, pady=12).pack(fill="x")
        self.entry.focus_set()

    def emit(self, kind, value):
        self.events.put((kind, value))

    def set_status(self, text):
        self.status_var.set(text)

    def greeting(self, text):
        name = self.config.display_name
        return f"{text}, {name}." if name else f"{text}."

    def add(self, role, text, citations=()):
        original = str(text)
        text = redact(original, self.config.api_key)
        if text != original:
            citations = ()
        self.chat.configure(state="normal")
        label = (self.config.display_name or role) if role == "User" else role
        self.chat.insert("end", label.upper() + "\n", role)
        cursor = 0
        for number, (start, end, url) in enumerate(citations):
            if not cursor <= start < end <= len(text):
                continue
            tag = f"citation-{len(self.messages)}-{number}"
            self.chat.tag_config(tag, foreground="#83c5ff", underline=True)
            self.chat.tag_bind(tag, "<Enter>", lambda _event: self.chat.configure(cursor="hand2"))
            self.chat.tag_bind(tag, "<Leave>", lambda _event: self.chat.configure(cursor="xterm"))
            self.chat.tag_bind(tag, "<Button-1>", lambda _event, target=url: self.open_citation(target))
            self.chat.insert("end", text[cursor:start])
            self.chat.insert("end", text[start:end], tag)
            cursor = end
        self.chat.insert("end", text[cursor:] + "\n\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")
        self.messages.append({"role": role, "text": text, "time": dt.datetime.now().astimezone().isoformat()})
        # Persist display messages only, never credentials or hidden reasoning.
        try:
            atomic_json(self.session_path, {"version": VERSION, "messages": self.messages})
        except OSError as exc:
            self.set_status("Could not save the local conversation: " + str(exc))

    def open_citation(self, url):
        try:
            open_in_firefox(url)
        except (OSError, ValueError):
            self.set_status("Could not open the source in Firefox.")

    def set_busy(self, busy, kind=""):
        self.busy = busy
        self.job_kind = kind if busy else ""
        for button in (self.send_button, self.voice_button, self.settings_button, self.new_button):
            button.configure(state="disabled" if busy else "normal")
        self.stop_button.configure(state="normal" if busy else "disabled")
        self.talk_button.configure(state="normal" if not busy or kind == "record" else "disabled",
                                   text="Finish speaking" if kind == "record" and busy else "Talk")

    def job(self, kind, action):
        if self.busy:
            return
        self.cancel.clear()
        self.record_finishing = False
        self.set_busy(True, kind)

        def run():
            try:
                action()
            except Cancelled:
                self.emit("cancelled", None)
            except Exception as exc:
                self.emit("error", friendly_error(exc, self.config.api_key))
            finally:
                self.emit("done", None)

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "status":
                    self.set_status(value)
                    if self.job_kind == "record" and value.startswith(("Recognizing", "Thinking", "Speaking")):
                        self.talk_button.configure(state="disabled", text="Talk")
                elif kind == "tool":
                    self.add("Tool", value)
                elif kind == "heard":
                    self.add("User", value)
                elif kind == "answer":
                    self.last_answer, citations = value
                    self.add("Jarvis", self.last_answer, citations)
                elif kind == "error":
                    self.add("System", value)
                    self.set_status("Needs attention — see message above")
                elif kind == "cancelled":
                    self.add("System", "Stopped. Any tool actions already completed are listed above.")
                elif kind == "approval":
                    self.review_command(*value)
                elif kind == "done":
                    self.set_busy(False)
                    if self.cancel.is_set():
                        self.set_status("Stopped")
                    elif self.status_var.get().startswith(("Thinking", "Speaking", "Listening", "Recognizing", "Testing")):
                        self.set_status("Ready • " + self.config.model)
                    self.entry.focus_set()
        except queue.Empty:
            pass
        self.root.after(60, self.poll)

    def enter(self, event):
        if event.state & 0x1:  # Shift+Enter adds a line.
            return None
        self.send()
        return "break"

    def send(self):
        if self.busy:
            return
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return
        if not self.config.api_key:
            self.settings()
            return
        self.entry.delete("1.0", "end")
        self.add("User", text)
        self.job("think", lambda: self.answer(text))

    def answer(self, text):
        self.emit("status", "Thinking in the cloud…")
        answer = self.brain.ask(text, self.cancel)
        citations = self.brain.last_citations
        self.emit("answer", (answer, citations))
        usage = self.brain.last_usage
        self.emit("status", f"Ready • {self.config.model} • API tokens this turn: "
                  f"{usage.get('input_tokens', 0)} in / {usage.get('output_tokens', 0)} out")
        if self.config.speak_replies and not self.cancel.is_set():
            self.emit("status", "Speaking locally…")
            self.audio.speak(without_citations(answer, citations))

    def talk(self):
        if self.busy and self.job_kind == "record":
            if not self.record_finishing:
                self.record_finishing = True
                self.audio.end_recording()
                self.talk_button.configure(state="disabled", text="Recognizing…")
                self.set_status("Recognizing your speech locally…")
            return
        if self.busy:
            return
        if not self.config.api_key:
            self.settings()
            return
        self.audio.prepare_recording()

        def record_and_answer():
            self.emit("status", "Listening — microphone starting…")
            source = self.audio.record(lambda value: self.emit("status", value))
            if source is None or self.cancel.is_set():
                raise Cancelled()
            self.emit("status", "Recognizing your speech locally…")
            text = self.audio.transcribe(source)
            if self.cancel.is_set():
                raise Cancelled()
            self.emit("heard", text)
            self.answer(text)

        self.job("record", record_and_answer)

    def speak(self, text):
        if self.busy:
            return
        self.set_status("Speaking locally…")
        self.job("speak", lambda: self.audio.speak(text))

    def stop(self):
        self.cancel.set()
        self.audio.cancel_recording()
        self.audio.stop_speech()
        self.set_status("Stopping… A cloud request already sent may take up to 60 seconds to return.")
        self.talk_button.configure(state="disabled")

    def approve(self, command, directory):
        request = {"done": threading.Event(), "approved": False}
        self.emit("approval", (command, directory, request))
        while not request["done"].wait(0.1):
            if self.cancel.is_set() or self.closed:
                return False
        return request["approved"] and not self.cancel.is_set()

    def review_command(self, command, directory, request):
        if self.cancel.is_set():
            request["done"].set()
            return
        top = tk.Toplevel(self.root)
        top.title("Run this Ubuntu command?")
        top.configure(bg=BG)
        top.geometry("760x360")
        top.transient(self.root)
        self.review_windows.append(top)
        tk.Label(top, text="Jarvis wants to run this command", bg=BG, fg=TEXT,
                 font=("DejaVu Sans", 14, "bold")).pack(anchor="w", padx=20, pady=16)
        tk.Label(top, text="Folder: " + directory, bg=BG, fg=MUTED, wraplength=700).pack(anchor="w", padx=20)
        code = scrolledtext.ScrolledText(top, bg=PANEL, fg=TEXT, height=7, font=("DejaVu Sans Mono", 11))
        code.pack(fill="both", expand=True, padx=20, pady=12)
        code.insert("1.0", command)
        code.configure(state="disabled")

        def finish(approved):
            request["approved"] = approved
            request["done"].set()
            if top in self.review_windows:
                self.review_windows.remove(top)
            top.destroy()

        buttons = ttk.Frame(top, padding=14)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Run command", command=lambda: finish(True)).pack(side="right")
        ttk.Button(buttons, text="Decline", command=lambda: finish(False)).pack(side="right", padx=8)
        top.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        top.grab_set()

    def settings(self):
        if self.busy:
            return
        top = tk.Toplevel(self.root)
        top.title("Jarvis settings")
        top.configure(bg=BG)
        top.resizable(False, False)
        top.transient(self.root)
        top.grab_set()
        form = ttk.Frame(top, padding=22)
        form.pack(fill="both", expand=True)
        ttk.Label(form, text="Cloud connection", font=("DejaVu Sans", 14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        key = tk.StringVar(value=self.config.api_key)
        model = tk.StringVar(value=self.config.model)
        folder = tk.StringVar(value=self.config.workspace)
        ttk.Label(form, text="OpenAI API key").grid(row=1, column=0, sticky="w", pady=7)
        ttk.Entry(form, textvariable=key, show="•", width=48).grid(row=1, column=1, columnspan=2, sticky="ew")
        ttk.Label(form, text="Model").grid(row=2, column=0, sticky="w", pady=7)
        ttk.Combobox(form, textvariable=model, width=45,
                     values=["gpt-6.2-sol", "gpt-6.2-astra", "gpt-6-luna", "gpt-5.4-mini"]).grid(row=2, column=1, columnspan=2, sticky="ew")
        ttk.Label(form, text="Uses your OpenAI API account and its available credits.\n"
                  "The key is saved in a private file on this computer.", foreground=MUTED,
                  font=("DejaVu Sans", 9)).grid(row=3, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Label(form, text="Working folder").grid(row=4, column=0, sticky="w", pady=7)
        ttk.Entry(form, textvariable=folder, width=36).grid(row=4, column=1, sticky="ew")

        def browse():
            chosen = filedialog.askdirectory(parent=top, initialdir=str(Path(folder.get()).expanduser()))
            if chosen:
                folder.set(chosen)

        ttk.Button(form, text="Choose…", command=browse).grid(row=4, column=2, padx=(8, 0))
        input_devices, output_devices = {"System default": None}, {"System default": None}
        device_error = ""
        try:
            for device in Audio.devices():
                label = f"{device['index']}: {device['name']}"
                if device["max_input_channels"] > 0:
                    input_devices[label] = device["index"]
                if device["max_output_channels"] > 0:
                    output_devices[label] = device["index"]
        except Exception as exc:
            device_error = str(exc)

        def current_label(items, value):
            return next((label for label, index in items.items() if index == value), "System default")

        mic = tk.StringVar(value=current_label(input_devices, self.config.microphone))
        speaker = tk.StringVar(value=current_label(output_devices, self.config.speaker))
        for row, label, variable, options in [(5, "Microphone", mic, input_devices), (6, "Speaker", speaker, output_devices)]:
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=7)
            ttk.Combobox(form, textvariable=variable, values=list(options), state="readonly", width=45).grid(row=row, column=1, columnspan=2, sticky="ew")
        values = {}
        for row, field, label in [(7, "speak_replies", "Speak replies using the local Piper voice"),
                                  (8, "startup_announcement", 'Play a greeting on startup'),
                                  (9, "computer_tools", "Enable local computer tools"),
                                  (10, "review_commands", "Review terminal commands before running")]:
            values[field] = tk.BooleanVar(value=getattr(self.config, field))
            ttk.Checkbutton(form, text=label, variable=values[field]).grid(row=row, column=0, columnspan=3, sticky="w", pady=5)
        ttk.Label(form, text="Voice: British male (Alan). Speech recognition runs locally.\n"
                  "This app starts a separate conversation from your ChatGPT history.", foreground=MUTED,
                  font=("DejaVu Sans", 9)).grid(row=11, column=0, columnspan=3, sticky="w", pady=10)
        if device_error:
            ttk.Label(form, text="Audio device issue: " + device_error[:160], wraplength=560,
                      foreground="#ffb4a9").grid(row=12, column=0, columnspan=3, sticky="w", pady=5)

        display_name = tk.StringVar(value=self.config.display_name)
        ttk.Label(form, text="Your name (optional)").grid(row=13, column=0, sticky="w", pady=7)
        ttk.Entry(form, textvariable=display_name, width=36).grid(row=13, column=1, columnspan=2, sticky="ew")

        def save():
            try:
                updated = dataclasses.replace(self.config)
                updated.display_name = " ".join(display_name.get().split())
                updated.api_key = key.get().strip()
                updated.model = model.get().strip()
                if not updated.model:
                    raise ValueError("Enter a cloud model name.")
                updated.workspace = str(Path(folder.get()).expanduser().resolve())
                Path(updated.workspace).mkdir(parents=True, exist_ok=True)
                updated.microphone, updated.speaker = input_devices[mic.get()], output_devices[speaker.get()]
                for field, value in values.items():
                    setattr(updated, field, value.get())
                updated.save()
                old_turns = self.brain.turns
                self.config = updated
                self.audio = Audio(updated)
                self.brain = Brain(updated, self.approve, self.emit)
                self.brain.turns = old_turns
                top.destroy()
                self.set_status("Ready • " + updated.model if updated.api_key else "Voice ready • Cloud key needed")
                self.add("System", "Settings saved. Working folder: " + updated.workspace)
            except Exception as exc:
                messagebox.showerror("Settings", friendly_error(exc, self.config.api_key), parent=top)

        ttk.Button(form, text="Save settings", style="Gold.TButton", command=save).grid(row=14, column=1, columnspan=2, sticky="e", pady=(10, 0))

    def new_chat(self):
        if self.busy:
            return
        self.brain.turns.clear()
        self.messages.clear()
        self.last_answer = ""
        self.session_path = paths()["state"] / "conversations" / (dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.add("Jarvis", self.greeting("Ready for a new conversation"))

    def export(self):
        target = filedialog.asksaveasfilename(parent=self.root, defaultextension=".txt", initialfile="Jarvis_conversation.txt",
                                             filetypes=[("Text", "*.txt")])
        if target:
            try:
                Path(target).write_text("\n\n".join(item["role"] + ":\n" + item["text"] for item in self.messages), encoding="utf-8")
                self.set_status("Conversation saved to " + target)
            except OSError as exc:
                messagebox.showerror("Save chat", str(exc), parent=self.root)

    def close(self):
        self.closed = True
        self.cancel.set()
        self.audio.cancel_recording()
        self.audio.stop_speech()
        if self.worker is not None and self.worker.is_alive():
            # Give an active command's cancellation loop time to kill its process group.
            # A pending HTTP request runs in a daemon thread and cannot launch more tools.
            self.worker.join(timeout=0.35)
        self.root.destroy()


def main():
    os.umask(0o077)
    root = tk.Tk()
    try:
        App(root)
    except Exception as exc:
        messagebox.showerror("Jarvis could not start", str(exc), parent=root)
        root.destroy()
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
