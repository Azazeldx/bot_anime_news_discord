import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import history_store


class HistoryTests(unittest.TestCase):
    def test_merge_migrates_legacy_and_preserves_both_runs(self):
        result = history_store.merge(["base", "remote"], {
            "sent": ["base", "local"], "areaanime_seen": ["local"],
            "areaanime_posts": [{"link": "local", "key": "topic", "title": "Title",
                                 "ts": "2026-10-01T00:00:00+00:00"}],
        })
        self.assertEqual(result["sent"], ["remote", "base", "local"])
        self.assertEqual(set(result["areaanime_seen"]), {"base", "remote", "local"})
        self.assertEqual(len(result["areaanime_posts"]), 1)
        self.assertEqual(history_store.merge(result, result), result)

    def test_history_limits_apply_after_deduplication(self):
        links = [str(i) for i in range(history_store.HISTORY_LIMIT + 5)]
        result = history_store.merge({}, {"sent": links + [links[0]]})
        self.assertEqual(len(result["sent"]), history_store.HISTORY_LIMIT)
        self.assertEqual(result["sent"][-1], links[0])

    def test_corrupted_history_is_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.json"
            path.write_text("not JSON", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                history_store.load(path)
        with self.assertRaises(ValueError):
            history_store.normalize({"sent": "not a list"})

    def test_atomic_save_failure_keeps_previous_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.json"
            history_store.save(path, {"sent": ["old"]})
            before = path.read_bytes()
            with patch.object(history_store.os, "replace", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    history_store.save(path, {"sent": ["new"]})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    @unittest.skipUnless(shutil.which("git"), "Git required for integration test")
    def test_git_rebase_merges_divergent_history_without_losing_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)

            def git(*args):
                return subprocess.run(["git", *args], cwd=root, check=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            git("init", "-b", "main")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.com")
            # Quote executable paths for Windows installations containing spaces.
            executable = Path(sys.executable).as_posix()
            driver = Path(history_store.__file__).as_posix()
            git("config", "merge.news-history.driver", f'"{executable}" "{driver}" --merge "%A" "%B"')
            (root / ".gitattributes").write_text("history.json merge=news-history\n", encoding="utf-8")
            path = root / "history.json"
            history_store.save(path, {"sent": ["base"]})
            git("add", ".")
            git("commit", "-m", "base")
            git("checkout", "-b", "local-run")
            history_store.save(path, {"sent": ["base", "local"]})
            git("commit", "-am", "local delivery")
            git("checkout", "main")
            history_store.save(path, {"sent": ["base", "remote"]})
            git("commit", "-am", "remote delivery")
            git("checkout", "local-run")
            git("rebase", "main")
            self.assertEqual(set(history_store.load(path)["sent"]), {"base", "remote", "local"})
            self.assertEqual(git("status", "--porcelain").stdout, "")
