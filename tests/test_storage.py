"""数据目录解析与初始化的单元测试。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vigi import storage


class ResolveDataDirTests(unittest.TestCase):
    """三级优先级：--dir > vigi_DIR > 默认目录。"""

    def test_cli_dir_has_highest_priority(self) -> None:
        env = {storage.ENV_VAR: "/from/env"}
        result = storage.resolve_data_dir("/from/cli", env=env, home="/home/u")
        self.assertEqual(result, Path("/from/cli"))

    def test_env_used_when_no_cli(self) -> None:
        env = {storage.ENV_VAR: "/from/env"}
        result = storage.resolve_data_dir(None, env=env, home="/home/u")
        self.assertEqual(result, Path("/from/env"))

    def test_default_when_nothing_set(self) -> None:
        result = storage.resolve_data_dir(None, env={}, home="/home/u")
        self.assertEqual(result, Path("/home/u/.local/share/vigi"))

    def test_empty_env_falls_back_to_default(self) -> None:
        env = {storage.ENV_VAR: ""}
        result = storage.resolve_data_dir(None, env=env, home="/home/u")
        self.assertEqual(result, Path("/home/u/.local/share/vigi"))

    def test_cli_dir_expands_tilde(self) -> None:
        with mock.patch.dict(os.environ, {"HOME": "/home/u"}):
            result = storage.resolve_data_dir("~/vigi", env={}, home="/home/u")
        self.assertEqual(result, Path("/home/u/vigi"))

    def test_env_value_expands_tilde(self) -> None:
        env = {storage.ENV_VAR: "~/vigi"}
        with mock.patch.dict(os.environ, {"HOME": "/home/u"}):
            result = storage.resolve_data_dir(None, env=env)
        self.assertEqual(result, Path("/home/u/vigi"))


class ReadTextSafeTests(unittest.TestCase):
    def test_missing_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(storage.read_text_safe(Path(tmp) / "nope.md"))

    def test_non_utf8_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.md"
            path.write_bytes(b"\xff\xfe\x00")
            self.assertIsNone(storage.read_text_safe(path))

    def test_ok_returns_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ok.md"
            storage.write_text(path, "x")
            self.assertEqual(storage.read_text_safe(path), "x")


class ResolveSourceTests(unittest.TestCase):
    def test_cli_source(self) -> None:
        result = storage.resolve_data_dir_with_source(
            "/x", env={storage.ENV_VAR: "/y"}, home="/h"
        )
        self.assertEqual(result, (Path("/x"), "cli"))

    def test_env_source(self) -> None:
        result = storage.resolve_data_dir_with_source(
            None, env={storage.ENV_VAR: "/y"}, home="/h"
        )
        self.assertEqual(result, (Path("/y"), "env"))

    def test_default_source(self) -> None:
        result = storage.resolve_data_dir_with_source(None, env={}, home="/h")
        self.assertEqual(result, (Path("/h/.local/share/vigi"), "default"))


class EnsureDataDirsTests(unittest.TestCase):
    def test_creates_data_dir_and_subdirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "vigidata"
            result = storage.ensure_data_dirs(data_dir)
            self.assertEqual(result, data_dir)
            self.assertTrue(data_dir.is_dir())
            for name in storage.SUBDIRS:
                self.assertTrue((data_dir / name).is_dir(), name)

    def test_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "vigidata"
            storage.ensure_data_dirs(data_dir)
            storage.ensure_data_dirs(data_dir)  # 不应抛异常
            self.assertTrue(data_dir.is_dir())

    def test_accepts_str(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "vigidata"
            storage.ensure_data_dirs(str(data_dir))
            self.assertTrue(data_dir.is_dir())


class AtomicWriteTests(unittest.TestCase):
    """原子写：内容正确、失败不破坏原文件、无残留临时文件。"""

    def test_write_then_read_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "f.md"
            storage.write_text(path, "内容\n")
            self.assertEqual(storage.read_text(path), "内容\n")

    def test_replace_failure_keeps_original_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.md"
            storage.write_text(path, "original\n")
            with mock.patch(
                "vigi.storage.os.replace", side_effect=OSError("boom")
            ):
                with self.assertRaises(OSError):
                    storage.write_text(path, "new\n")
            self.assertEqual(storage.read_text(path), "original\n")
            leftovers = [name for name in os.listdir(tmp) if name.startswith(".tmp-")]
            self.assertEqual(leftovers, [])

    def test_write_text_if_changed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.md"
            self.assertTrue(storage.write_text_if_changed(path, "a\n"))
            self.assertFalse(storage.write_text_if_changed(path, "a\n"))
            self.assertTrue(storage.write_text_if_changed(path, "b\n"))
            self.assertEqual(storage.read_text(path), "b\n")

    def test_read_text_if_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.md"
            self.assertIsNone(storage.read_text_if_exists(path))
            storage.write_text(path, "x")
            self.assertEqual(storage.read_text_if_exists(path), "x")


class PathHelperTests(unittest.TestCase):
    def test_project_and_day_paths(self) -> None:
        from datetime import date

        self.assertEqual(
            storage.project_path("/data", "frankfurt-hps"),
            Path("/data/projects/frankfurt-hps.md"),
        )
        self.assertEqual(
            storage.day_path("/data", date(2026, 10, 1)),
            Path("/data/days/2026-10-01.md"),
        )

    def test_list_project_ids_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = storage.projects_dir(tmp)
            directory.mkdir(parents=True)
            (directory / "b.md").write_text("", encoding="utf-8")
            (directory / "a.md").write_text("", encoding="utf-8")
            (directory / "notes.txt").write_text("", encoding="utf-8")
            self.assertEqual(storage.list_project_ids(tmp), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
