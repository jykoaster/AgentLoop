"""openspec_runner 的 archive 目標命名與「讓出既有 archive」邏輯。不呼叫 openspec CLI。"""
import json
from pathlib import Path
from unittest.mock import patch

from AgentLoop.lib.openspec_runner import (
    archive_change,
    archive_destination_name,
    vacate_existing_archive,
)


class TestArchiveDestinationName:
    def test_undated_change_gets_today_prefix(self):
        assert archive_destination_name("feat-login", today="2026-09-23") == (
            "2026-09-23-feat-login"
        )

    def test_dated_change_keeps_its_name(self):
        name = "2026-09-23-70-feat-access-log-ui-and-api"
        assert archive_destination_name(name, today="2026-09-24") == name

    def test_uses_local_today_when_omitted(self):
        with patch("AgentLoop.lib.openspec_runner.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-01-02"
            assert archive_destination_name("feat-x") == "2026-01-02-feat-x"


def _touch_archive(project: Path, name: str) -> Path:
    path = project / "openspec" / "changes" / "archive" / name
    path.mkdir(parents=True)
    (path / "proposal.md").write_text("old", encoding="utf-8")
    return path


class TestVacateExistingArchive:
    def test_noop_when_missing(self, tmp_path):
        vacated, error = vacate_existing_archive(str(tmp_path), "2026-09-23-feat-x")
        assert vacated is None
        assert error == ""

    def test_renames_existing_to_suffix_2(self, tmp_path):
        dest = "2026-09-23-70-feat-access-log-ui-and-api"
        original = _touch_archive(tmp_path, dest)

        vacated, error = vacate_existing_archive(str(tmp_path), dest)

        assert error == ""
        assert vacated == f"{dest}-2"
        assert not original.exists()
        assert (tmp_path / "openspec" / "changes" / "archive" / vacated / "proposal.md").is_file()

    def test_skips_taken_suffix(self, tmp_path):
        dest = "2026-09-23-feat-x"
        _touch_archive(tmp_path, dest)
        _touch_archive(tmp_path, f"{dest}-2")

        vacated, error = vacate_existing_archive(str(tmp_path), dest)

        assert error == ""
        assert vacated == f"{dest}-3"
        archive_dir = tmp_path / "openspec" / "changes" / "archive"
        assert (archive_dir / f"{dest}-2").is_dir()
        assert (archive_dir / f"{dest}-3").is_dir()
        assert not (archive_dir / dest).exists()

    def test_rejects_unsafe_name(self, tmp_path):
        vacated, error = vacate_existing_archive(str(tmp_path), "../escape")
        assert vacated is None
        assert error


class TestArchiveChangeVacatesFirst:
    def test_vacates_then_calls_cli(self, tmp_path):
        dest = "2026-09-23-70-feat-access-log-ui-and-api"
        _touch_archive(tmp_path, dest)
        cli_payload = {"archive": {"archivedAs": dest}}

        with patch("AgentLoop.lib.openspec_runner.shutil.which", return_value="/usr/bin/openspec"), \
             patch("AgentLoop.lib.openspec_runner.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps(cli_payload)
            mock_run.return_value.stderr = ""
            result = archive_change(str(tmp_path), dest)

        assert result.ok
        assert result.data["vacated_as"] == f"{dest}-2"
        mock_run.assert_called_once()
        assert mock_run.call_args.args[0] == ["openspec", "archive", dest, "--yes", "--json"]
        assert not (tmp_path / "openspec" / "changes" / "archive" / dest).exists()

    def test_does_not_call_cli_when_vacate_fails(self, tmp_path):
        with patch("AgentLoop.lib.openspec_runner.vacate_existing_archive",
                   return_value=(None, "無法改名")), \
             patch("AgentLoop.lib.openspec_runner.subprocess.run") as mock_run:
            result = archive_change(str(tmp_path), "feat-x")

        assert not result.ok
        assert result.error_text == "無法改名"
        mock_run.assert_not_called()
