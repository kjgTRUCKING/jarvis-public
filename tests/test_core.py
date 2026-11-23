# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Brain, Cancelled, Config, ToolRunner, paths, redact


class LocalFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config"),
                                          "XDG_DATA_HOME": str(self.root / "data"),
                                          "XDG_STATE_HOME": str(self.root / "state")})
        self.env.start()
        self.config = Config(workspace=str(self.root / "work"), api_key="sk-private-test-secret-value", computer_tools=True)
        self.runner = ToolRunner(self.config, lambda *_: True)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()


class LocalTests(LocalFixture):
    def test_credentials_are_private_and_not_in_settings_or_repr(self):
        self.config.save()
        saved = Config.load()
        self.assertEqual(saved.api_key, self.config.api_key)
        folder = paths()["config"]
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
        self.assertEqual((folder / "credentials.json").stat().st_mode & 0o777, 0o600)
        self.assertNotIn(self.config.api_key, (folder / "settings.json").read_text())
        self.assertNotIn(self.config.api_key, repr(self.config))

    def test_writes_backup_original_and_preserve_executable_mode(self):
        target = self.runner.root / "script.sh"
        target.write_text("original")
        target.chmod(0o755)
        result = self.runner.write_file("script.sh", "updated")
        self.assertEqual(Path(result["backup"]).read_text(), "original")
        self.assertEqual(target.read_text(), "updated")
        self.assertEqual(target.stat().st_mode & 0o777, 0o755)

    def test_file_tools_reject_traversal_symlinks_and_secrets(self):
        (self.root / "outside").mkdir()
        (self.runner.root / "link").symlink_to(self.root / "outside", target_is_directory=True)
        for name in ["../outside/file", "link/file", ".env", ".env.production", ".ssh/id_ed25519"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.runner.write_file(name, "x")

    def test_declining_command_has_no_side_effect(self):
        self.runner.approve = lambda *_: False
        result = self.runner.run_command("touch should-not-exist", ".")
        self.assertTrue(result["declined"])
        self.assertFalse((self.runner.root / "should-not-exist").exists())

    def test_command_result_exit_status_and_output_limit(self):
        result = self.runner.run_command("printf 'hello'; exit 7", ".")
        self.assertEqual(result["exit_code"], 7)
        self.assertEqual(result["output"], "hello")
        result = self.runner.run_command("head -c 18000 /dev/zero", ".")
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["output"]), 14000)

    def test_cancel_kills_command_before_later_write(self):
        self.runner.config.review_commands = False
        timer = threading.Timer(0.15, self.runner.cancel.set)
        timer.start()
        try:
            with self.assertRaises(Cancelled):
                self.runner.run_command("sleep 0.8; touch never-created", ".")
        finally:
            timer.join()
        time.sleep(0.85)
        self.assertFalse((self.runner.root / "never-created").exists())

    def test_redaction_and_child_environment(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "example", "A_TOKEN": "example", "A_PASSWORD": "example", "NORMAL_VAR": "yes"}):
            env = self.runner._child_env()
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("A_TOKEN", env)
        self.assertNotIn("A_PASSWORD", env)
        self.assertEqual(env["NORMAL_VAR"], "yes")
        self.assertNotIn(self.config.api_key, redact(self.config.api_key, self.config.api_key))

    def test_untrusted_url_scheme_and_admin_command_rejected(self):
        for url in ["file:///etc/passwd", "javascript:alert(1)", "https://user:password@example.com"]:
            with self.assertRaises(ValueError):
                self.runner.open_url(url)
        with self.assertRaises(ValueError):
            self.runner.run_command("sudo apt update", ".")


def response(output):
    return {"id": "resp_test", "object": "response", "created_at": 1, "status": "completed",
            "model": "gpt-6.2-sol", "output": output,
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}


def message(text):
    return {"id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}]}


class CloudProtocolTests(LocalFixture):
    def client(self, handler):
        import httpx2 as httpx
        from openai import OpenAI
        return OpenAI(api_key="dummy-not-a-real-key", base_url="https://jarvis-test.invalid/v1",
                      max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    def test_real_sdk_tool_round_trip_and_conversation_continuity(self):
        import httpx2 as httpx
        requests = []
        def handler(request):
            payload = json.loads(request.content)
            requests.append(payload)
            self.assertFalse(payload["store"])
            self.assertIn("reasoning.encrypted_content", payload["include"])
            if len(requests) == 1:
                result = response([{"id": "rs_1", "type": "reasoning", "summary": [], "encrypted_content": "test-encrypted-context"},
                    {"id": "fc_1", "type": "function_call", "name": "write_file",
                    "arguments": json.dumps({"path": "hello.txt", "content": "Hello Jarvis"}), "call_id": "call_1"}])
            else:
                if len(requests) == 2:
                    reasoning = next(item for item in payload["input"] if item.get("type") == "reasoning")
                    self.assertEqual(reasoning["encrypted_content"], "test-encrypted-context")
                    outputs = [item for item in payload["input"] if item.get("type") == "function_call_output"]
                    self.assertEqual(outputs[-1]["call_id"], "call_1")
                    self.assertIn("written", json.loads(outputs[-1]["output"]))
                result = response([message("Saved hello.txt.")])
            return httpx.Response(200, json=result)
        client = self.client(handler)
        brain = Brain(self.config, lambda *_: True, client=client)
        try:
            self.assertEqual(brain.ask("Create a file", threading.Event()), "Saved hello.txt.")
            self.assertEqual((self.runner.root / "hello.txt").read_text(), "Hello Jarvis")
            brain.ask("What did we just do?", threading.Event())
            roles = [item.get("role") for item in requests[-1]["input"]]
            self.assertEqual(roles.count("user"), 2)
            self.assertIn("assistant", roles)
            self.assertEqual(brain.last_usage, {"input_tokens": 10, "output_tokens": 5})
        finally:
            client.close()

    def test_cancel_after_network_response_prevents_tool_execution(self):
        import httpx2 as httpx
        cancel = threading.Event()
        def handler(request):
            cancel.set()
            return httpx.Response(200, json=response([{"id": "fc", "type": "function_call", "name": "write_file",
                "arguments": json.dumps({"path": "no.txt", "content": "no"}), "call_id": "no"}]))
        client = self.client(handler)
        try:
            brain = Brain(self.config, lambda *_: True, client=client)
            with self.assertRaises(Cancelled):
                brain.ask("go", cancel)
            self.assertFalse((self.runner.root / "no.txt").exists())
            self.assertEqual(brain.turns, [])
        finally:
            client.close()

    def test_tool_budget_finishes_without_more_tools(self):
        import httpx2 as httpx
        count = 0
        def handler(request):
            nonlocal count
            count += 1
            payload = json.loads(request.content)
            if count == 10:
                self.assertNotIn("tools", payload)
                result = response([message("Here are the results.")])
            else:
                result = response([{"id": f"fc_{count}", "type": "function_call", "name": "system_info",
                                    "arguments": "{}", "call_id": f"call_{count}"}])
            return httpx.Response(200, json=result)
        client = self.client(handler)
        try:
            self.assertEqual(Brain(self.config, lambda *_: True, client=client).ask("test", threading.Event()), "Here are the results.")
            self.assertEqual(count, 10)
        finally:
            client.close()

    def test_api_failure_does_not_commit_incomplete_conversation(self):
        import httpx2 as httpx
        def handler(request):
            return httpx.Response(401, json={"error": {"message": "bad key", "type": "invalid_request_error"}})
        client = self.client(handler)
        try:
            brain = Brain(self.config, lambda *_: True, client=client)
            with self.assertRaises(Exception):
                brain.ask("test", threading.Event())
            self.assertEqual(brain.turns, [])
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
