"""Voice-friendly desktop actions with fixed commands and workspace paths."""

import ast
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import tempfile

DOCUMENT_TYPES = {".pdf", ".txt", ".md", ".csv", ".jpg", ".jpeg", ".png"}
OFFICE_TYPES = {".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp"}
PRINTER = "ENVY_Photo_7800"


class DesktopActions:
    def capture_camera(self, camera: str, mode: str, seconds: int, channel: int | None):
        if camera not in {"ubuntu", "annke"} or mode not in {"photo", "video"}:
            raise ValueError("Choose Ubuntu camera or ANNKE, and a photo or video.")
        helper = Path(__file__).resolve().parents[2] / "camera_capture.py"
        command = ["/usr/bin/python3", str(helper), camera, mode, "--seconds", str(seconds)]
        if channel is not None:
            command.extend(["--channel", str(channel)])
        completed = subprocess.run(
            command,
            capture_output=True, text=True, timeout=48, env=self._child_env(),
        )
        try:
            return json.loads(completed.stdout)
        except ValueError as error:
            raise RuntimeError("The camera capture service could not run.") from error

    def _desktop_command(self, *command, timeout=15):
        # Desktop programs may inherit the launcher's file descriptors.
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stdout, \
                tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr:
            result = subprocess.run(
                command, stdout=stdout, stderr=stderr, timeout=timeout, env=self._child_env()
            )
            if result.returncode:
                stderr.seek(0)
                raise RuntimeError(stderr.read().strip() or f"{command[0]} failed.")
            stdout.seek(0)
            return stdout.read().strip()

    def _launch_desktop(self, *command):
        # The wake service exits after each reply. Keep the GUI out of its process group.
        return self._desktop_command("systemd-run", "--user", "--scope", "--quiet", "--", *command)

    def open_program(self, name: str):
        output = self._launch_desktop("/usr/bin/python3", "-c", """
from gi.repository import Gio
import sys

name = sys.argv[1].strip().casefold()
apps = [app for app in Gio.AppInfo.get_all() if app.should_show()]
exact = [app for app in apps if name in (app.get_display_name().casefold(), (app.get_id() or "").casefold())]
matches = exact or [app for app in apps if name in app.get_display_name().casefold()]
if not name or len(matches) != 1:
    candidates = ", ".join(app.get_display_name() for app in matches[:8])
    sys.exit("Specify one installed application." + (" Matches: " + candidates if candidates else ""))
app = matches[0]
if not app.launch([], None):
    sys.exit("The application did not accept the launch request.")
print(app.get_display_name())
""", name)
        return {"launch_requested": output}

    def _window_call(self, method, *args):
        output = self._desktop_command(
            "gdbus", "call", "--session", "--dest", "org.gnome.Shell",
            "--object-path", "/org/jarvis/Windows", "--method", f"org.jarvis.Windows.{method}", *args
        )
        return output

    def list_windows(self):
        return json.loads(ast.literal_eval(self._window_call("List"))[0])

    def close_window(self, name: str):
        name = name.strip().casefold()
        if not name:
            raise ValueError("Name the program or window to close.")
        windows = self.list_windows()
        labels = lambda window: ((window["app"] or "").casefold(), (window["title"] or "").casefold())
        exact = [window for window in windows if name in labels(window)]
        matches = exact or [window for window in windows if any(name in label for label in labels(window))]
        if len(matches) != 1:
            return {"error": "Specify one open window.", "matches": [window["title"] for window in matches]}
        window = matches[0]
        if self._window_call("Close", json.dumps(window["id"])) != "(true,)":
            raise RuntimeError("The selected window cannot be closed.")
        return {"close_requested": window["title"], "note": "The app may ask you to save changes."}

    def take_note(self, text: str):
        text = text.strip()
        if not text:
            raise ValueError("The note is empty.")
        target = self._path("Jarvis Notes.txt")
        fd = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            now = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
            stream.write(f"{now}\n{text}\n\n")
        return {"saved_to": target.name}

    def _document(self, path):
        target = self._path(path)
        if target.suffix.lower() not in DOCUMENT_TYPES | OFFICE_TYPES or not target.is_file():
            raise ValueError("Choose an existing PDF, text, image, or Office document in the working folder.")
        return target

    def open_document(self, path: str):
        target = self._document(path)
        self._launch_desktop("gio", "open", target.as_uri())
        return {"open_requested": target.name}

    def print_document(self, path: str):
        target = self._document(path)
        with tempfile.TemporaryDirectory(prefix="jarvis-print-") as folder:
            if target.suffix.lower() in OFFICE_TYPES:
                profile = (Path(folder) / "profile").as_uri()
                self._desktop_command(
                    "libreoffice", f"-env:UserInstallation={profile}", "--headless",
                    "--convert-to", "pdf", "--outdir", folder, str(target), timeout=45
                )
                target = Path(folder) / (target.stem + ".pdf")
                if not target.is_file():
                    raise RuntimeError("LibreOffice did not produce a printable PDF.")
            job = self._desktop_command("lp", "-d", PRINTER, "-n", "1", "--", str(target))
        return {"print_queue": PRINTER, "job": job}
