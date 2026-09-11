from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


PLUGIN = Path(__file__).resolve().parents[1]
TOOL = PLUGIN / "scripts" / "candidate.py"


class CandidateToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="sol-advisor-candidate-test.")
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Sol Advisor Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.repo / "tracked.txt").write_text("one\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("commit", "-qm", "fixture")
        self.manifest = self.base / "candidate.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", os.fspath(self.repo), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, os.fspath(TOOL), *args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def snapshot(self, *extra: str) -> dict[str, object]:
        result = self.tool(
            "snapshot",
            "--repo",
            os.fspath(self.repo),
            "--output",
            os.fspath(self.manifest),
            *extra,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def verify(self) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        result = self.tool("verify", "--manifest", os.fspath(self.manifest))
        return result, json.loads(result.stdout)

    def write_rehashed_manifest(self, value: dict[str, object]) -> None:
        identity = {"selection": value["selection"], "entries": value["entries"]}
        encoded = json.dumps(
            identity, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        value["candidate_id"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
        self.manifest.write_text(json.dumps(value), encoding="utf-8")

    def test_unchanged_candidate_ignores_head_only_change(self) -> None:
        snapshot = self.snapshot()
        self.assertEqual(self.git("status", "--porcelain").stdout, "")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["status"], "match")
        self.assertEqual(payload["candidate_id"], snapshot["candidate_id"])

        self.git("commit", "--allow-empty", "-qm", "metadata only")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["status"], "match")
        self.assertTrue(payload["head_changed"])

    def test_tracks_modified_deleted_and_new_worktree_paths(self) -> None:
        (self.repo / "untracked.txt").write_text("present\n", encoding="utf-8")
        self.snapshot()
        (self.repo / "tracked.txt").write_text("two\n", encoding="utf-8")
        (self.repo / "untracked.txt").unlink()
        (self.repo / "new.txt").write_text("new\n", encoding="utf-8")

        result, payload = self.verify()
        self.assertEqual(result.returncode, 1)
        changes = {(item["path"], item["change"]) for item in payload["changes"]}
        self.assertEqual(
            changes,
            {
                ("tracked.txt", "modified"),
                ("untracked.txt", "removed"),
                ("new.txt", "added"),
            },
        )

    def test_ignored_and_external_files_require_explicit_binding(self) -> None:
        ignored = self.repo / "ignored.txt"
        external = self.base / "external.txt"
        (self.repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        ignored.write_text("first\n", encoding="utf-8")
        external.write_text("first\n", encoding="utf-8")
        self.snapshot()
        ignored.write_text("second\n", encoding="utf-8")
        external.write_text("second\n", encoding="utf-8")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["changes"], [])

        self.snapshot(
            "--input",
            os.fspath(ignored),
            "--input",
            os.fspath(external),
        )
        ignored.unlink()
        external.write_text("third\n", encoding="utf-8")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 1)
        paths = {item["path"] for item in payload["changes"]}
        self.assertEqual(
            paths,
            {
                os.fspath(ignored.resolve(strict=False)),
                os.fspath(external.resolve(strict=False)),
            },
        )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_executable_bit_symlink_target_and_special_path_are_bound(self) -> None:
        script = self.repo / "run.sh"
        link = self.repo / "current"
        odd = self.repo / "odd\nname.txt"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        odd.write_text("before\n", encoding="utf-8")
        os.symlink("tracked.txt", link)
        self.git("add", "run.sh", "current", "odd\nname.txt")
        self.snapshot()

        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        link.unlink()
        os.symlink("odd\nname.txt", link)
        odd.write_text("after\n", encoding="utf-8")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            {item["path"] for item in payload["changes"]},
            {"run.sh", "current", "odd\nname.txt"},
        )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_explicit_symlink_binds_link_instead_of_following_it(self) -> None:
        first = self.base / "first.txt"
        second = self.base / "second.txt"
        link = self.base / "selected-link"
        first.write_text("same contents\n", encoding="utf-8")
        second.write_text("same contents\n", encoding="utf-8")
        os.symlink(first.name, link)
        self.snapshot("--input", os.fspath(link))

        link.unlink()
        os.symlink(second.name, link)
        result, payload = self.verify()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            payload["changes"],
            [
                {
                    "scope": "input",
                    "path": os.fspath(link.parent.resolve(strict=False) / link.name),
                    "change": "modified",
                }
            ],
        )

    def test_manifest_failures_and_output_inside_repo_fail_closed(self) -> None:
        result = self.tool(
            "snapshot",
            "--repo",
            os.fspath(self.repo),
            "--output",
            os.fspath(self.repo / "candidate.json"),
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "error")
        self.assertFalse((self.repo / "candidate.json").exists())

        self.manifest.write_text("{not-json", encoding="utf-8")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["status"], "error")

        self.snapshot()
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        value["entries"][0]["size"] = 999
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertIn("identifier", payload["error"])

        self.snapshot()
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        value["source"] = {}
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["status"], "error")
        self.assertIn("source", payload["error"])
        self.assertEqual(result.stderr, "")

        self.snapshot()
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        value["source"]["head"] = "not-a-git-object"
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["status"], "error")
        self.assertIn("source head", payload["error"])
        self.assertEqual(result.stderr, "")

        self.snapshot()
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        value["selection"]["future_selector"] = True
        identity = {"selection": value["selection"], "entries": value["entries"]}
        encoded = json.dumps(
            identity, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        value["candidate_id"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["status"], "error")
        self.assertIn("selection", payload["error"])
        self.assertEqual(result.stderr, "")

        self.snapshot()
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        value["future_top_level"] = True
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["status"], "error")
        self.assertIn("top-level", payload["error"])
        self.assertEqual(result.stderr, "")

        self.snapshot()
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        value["entries"][0]["future_entry_field"] = True
        identity = {"selection": value["selection"], "entries": value["entries"]}
        encoded = json.dumps(
            identity, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        value["candidate_id"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["status"], "error")
        self.assertIn("entry fields", payload["error"])
        self.assertEqual(result.stderr, "")

        self.snapshot()
        original = self.manifest.read_text(encoding="utf-8")
        self.manifest.write_text(
            '{"schema_version": 1,' + original.lstrip()[1:], encoding="utf-8"
        )
        result, payload = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["status"], "error")
        self.assertIn("duplicate JSON key", payload["error"])
        self.assertEqual(result.stderr, "")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO creation is unavailable")
    def test_unsupported_explicit_input_and_unreadable_file_fail_closed(self) -> None:
        fifo = self.base / "input.fifo"
        os.mkfifo(fifo)
        result = self.tool(
            "snapshot",
            "--repo",
            os.fspath(self.repo),
            "--output",
            os.fspath(self.manifest),
            "--input",
            os.fspath(fifo),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unsupported", json.loads(result.stdout)["error"])

        protected = self.repo / "protected.txt"
        protected.write_text("secretless fixture\n", encoding="utf-8")
        self.git("add", "protected.txt")
        self.snapshot()
        protected.chmod(0)
        try:
            result, payload = self.verify()
            if os.access(protected, os.R_OK):
                self.skipTest("current user can still read mode-000 files")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(payload["status"], "error")
        finally:
            protected.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_noncanonical_manifest_paths_and_boolean_schema_fail_closed(self) -> None:
        self.snapshot()
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        value["schema_version"] = True
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertIn("schema", payload["error"])
        self.assertEqual(result.stderr, "")

        self.snapshot()
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        value["repo"] = os.fspath(self.repo.resolve() / "child" / "..")
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        result, payload = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertIn("repo path", payload["error"])
        self.assertEqual(result.stderr, "")

        for malformed in ("./tracked.txt", "tracked.txt\0shadow", "bad\ud800path"):
            self.snapshot()
            value = json.loads(self.manifest.read_text(encoding="utf-8"))
            repo_entry = next(item for item in value["entries"] if item["scope"] == "repo")
            repo_entry["path"] = malformed
            self.write_rehashed_manifest(value)
            result, payload = self.verify()
            self.assertEqual(result.returncode, 2)
            self.assertIn("repository path", payload["error"])
            self.assertEqual(result.stderr, "")

        explicit = self.repo / "tracked.txt"
        self.snapshot("--input", os.fspath(explicit))
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        malformed = os.fspath(self.repo.resolve() / "child" / ".." / "tracked.txt")
        value["selection"]["explicit_inputs"] = [malformed]
        input_entry = next(item for item in value["entries"] if item["scope"] == "input")
        input_entry["path"] = malformed
        self.write_rehashed_manifest(value)
        result, payload = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertIn("explicit inputs", payload["error"])
        self.assertEqual(result.stderr, "")

    def test_unhashable_entry_enums_fail_closed(self) -> None:
        for field, malformed in (("scope", []), ("scope", {}), ("type", []), ("type", {})):
            self.snapshot()
            value = json.loads(self.manifest.read_text(encoding="utf-8"))
            value["entries"][0][field] = malformed
            self.write_rehashed_manifest(value)
            result, payload = self.verify()
            self.assertEqual(result.returncode, 2)
            self.assertEqual(payload["status"], "error")
            self.assertIn("entry", payload["error"])
            self.assertEqual(result.stderr, "")

    def test_gitlink_fails_closed_for_missing_present_and_changed_oid(self) -> None:
        first_oid = self.git("rev-parse", "HEAD").stdout.strip()
        tree = self.git("rev-parse", "HEAD^{tree}").stdout.strip()
        second_oid = self.git("commit-tree", tree, "-m", "second gitlink target").stdout.strip()

        def assert_gitlink_error(oid: str) -> None:
            self.git("update-index", "--add", "--cacheinfo", f"160000,{oid},submodule")
            result = self.tool(
                "snapshot",
                "--repo",
                os.fspath(self.repo),
                "--output",
                os.fspath(self.manifest),
            )
            self.assertEqual(result.returncode, 2)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("submodule", payload["error"])
            self.assertEqual(result.stderr, "")

        assert_gitlink_error(first_oid)
        (self.repo / "submodule").mkdir()
        (self.repo / "submodule" / "worktree.txt").write_text("present\n", encoding="utf-8")
        assert_gitlink_error(first_oid)
        assert_gitlink_error(second_oid)

    def test_staged_mode_and_object_id_changes_are_bound(self) -> None:
        def assert_tracked_changed() -> None:
            result, payload = self.verify()
            self.assertEqual(result.returncode, 1)
            self.assertEqual(payload["status"], "changed")
            self.assertEqual(
                payload["changes"],
                [{"scope": "repo", "path": "tracked.txt", "change": "modified"}],
            )

        self.snapshot()
        self.git("update-index", "--chmod=+x", "tracked.txt")
        self.assertFalse(bool((self.repo / "tracked.txt").stat().st_mode & stat.S_IXUSR))
        assert_tracked_changed()

        self.git("reset", "-q", "HEAD", "--", "tracked.txt")
        self.snapshot()
        object_result = subprocess.run(
            ["git", "-C", os.fspath(self.repo), "hash-object", "-w", "--stdin"],
            input="staged only\n",
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        staged_oid = object_result.stdout.strip()
        self.git("update-index", "--cacheinfo", f"100644,{staged_oid},tracked.txt")
        assert_tracked_changed()

        self.git("reset", "-q", "HEAD", "--", "tracked.txt")
        (self.repo / "tracked.txt").unlink()
        self.snapshot()
        self.git("update-index", "--cacheinfo", f"100644,{staged_oid},tracked.txt")
        assert_tracked_changed()

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_symlink_loop_cli_paths_fail_with_structured_exit_two(self) -> None:
        first = self.base / "loop-a"
        second = self.base / "loop-b"
        os.symlink(second.name, first)
        os.symlink(first.name, second)
        cases = [
            (
                "snapshot",
                "--repo",
                os.fspath(first),
                "--output",
                os.fspath(self.manifest),
            ),
            (
                "snapshot",
                "--repo",
                os.fspath(self.repo),
                "--output",
                os.fspath(first),
            ),
            (
                "snapshot",
                "--repo",
                os.fspath(self.repo),
                "--output",
                os.fspath(self.manifest),
                "--input",
                os.fspath(first / "child"),
            ),
            ("verify", "--manifest", os.fspath(first)),
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.tool(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["status"], "error")
                self.assertEqual(result.stderr, "")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_repository_parent_symlink_fails_closed(self) -> None:
        nested = self.repo / "nested"
        nested.mkdir()
        (nested / "item.txt").write_text("inside\n", encoding="utf-8")
        self.git("add", "nested/item.txt")

        external = self.base / "external-directory"
        external.mkdir()
        (external / "item.txt").write_text("outside\n", encoding="utf-8")
        (nested / "item.txt").unlink()
        nested.rmdir()
        os.symlink(external, nested)

        result = self.tool(
            "snapshot",
            "--repo",
            os.fspath(self.repo),
            "--output",
            os.fspath(self.manifest),
        )
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertIn("symlinked repository parent", payload["error"])
        self.assertEqual(result.stderr, "")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_manifest_rejects_impossible_symlink_target(self) -> None:
        link = self.repo / "bound-link"
        os.symlink("tracked.txt", link)
        self.snapshot()
        value = json.loads(self.manifest.read_text(encoding="utf-8"))
        link_entry = next(item for item in value["entries"] if item["type"] == "symlink")
        link_entry["target"] = ""
        link_entry["sha256"] = hashlib.sha256(b"").hexdigest()
        self.write_rehashed_manifest(value)
        result, payload = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertIn("symlink entry", payload["error"])
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
