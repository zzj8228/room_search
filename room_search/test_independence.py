"""Verify isolation and official-login persistence without a real account."""
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import auth, client, database, login
from .paths import ROOT, runtime_dir


class IsolationTests(unittest.TestCase):
    def test_browser_open_does_not_wait_for_daemon_output_eof(self):
        import subprocess
        with patch.object(login.shutil, "which", return_value="agent-browser.cmd"), \
             patch.object(login.subprocess, "run") as run:
            run.return_value.returncode = 0
            login._browser("--headed", "open", auth.HOME)
        self.assertEqual(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["stderr"], subprocess.DEVNULL)

    def test_project_local_paths_and_no_replay_env_fallback(self):
        with patch.dict(os.environ, {"PKU_REPLAY_DATA_DIR": "X:/replay-data"}, clear=True):
            self.assertEqual(runtime_dir(), ROOT / "data")
            with patch.object(database, "CONFIG", ROOT / "data/auth/absent-test-config"):
                with self.assertRaises(RuntimeError):
                    database.require_database_url()
            with self.assertRaises(ValueError):
                database.source_connection_url()
        self.assertEqual(auth.AUTH_FILE.parent, database.CONFIG.parent)
        self.assertNotEqual(auth.AUTH_FILE, database.CONFIG)

    def test_no_runtime_imports_from_replay(self):
        import sys
        for name in ["app", "db", "pku_auth", "app_paths"]:
            self.assertNotIn(name, sys.modules)

    def test_encrypted_session_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.dpapi"
            data = {"cookies": [{"name":"test", "value":"private-sentinel"}], "origins": []}
            auth.save_state(data, path)
            self.assertNotIn(b"private-sentinel", path.read_bytes())
            self.assertEqual(auth.load_state(path), data)

    def test_failed_official_validation_does_not_save_candidate(self):
        candidate = {"cookies": [{"name":"JSESSIONID", "value":"test", "domain":"course.pku.edu.cn"}]}
        with patch.object(auth, "_acquire_token", side_effect=auth.AuthError("login_required", "请登录")), \
             patch.object(auth, "save_state") as save:
            with self.assertRaises(auth.AuthError):
                auth.import_browser_cookies(candidate["cookies"])
            save.assert_not_called()

    def test_independent_browser_finishes_with_own_cookie_import(self):
        payload = {"success":True, "data":{"cookies":[{"name":"JSESSIONID", "value":"test", "domain":"course.pku.edu.cn"}]}}
        def inline_job(_phase, operation):
            operation()
            return login.status()
        with patch.object(login, "_job", side_effect=inline_job), \
             patch.object(login, "_browser", return_value=json.dumps(payload)) as browser, \
             patch.object(auth, "import_browser_cookies") as accept:
            result = login.finish()
        accept.assert_called_once_with(payload["data"]["cookies"])
        self.assertEqual(browser.call_args_list[0].args, ("cookies", "get", "--json"))
        self.assertEqual(result["status"], "done")

    def test_api_rejects_bad_auth_and_refreshes_only_once(self):
        import urllib.error
        error = urllib.error.HTTPError("https://onlineroomse.pku.edu.cn/", 401, "expired", {}, None)
        with patch.object(client.urllib.request, "urlopen", side_effect=error) as open_url, \
             patch.object(client, "acquire_token", return_value="refreshed") as refresh:
            with self.assertRaises(auth.AuthError):
                client.api_get("course-live/search-live-course-list", {}, "initial")
        self.assertEqual(open_url.call_count, 2)
        refresh.assert_called_once_with(force=True)


if __name__ == "__main__":
    unittest.main()
