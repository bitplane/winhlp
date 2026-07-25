"""Tests for command-line output mode selection."""

import json
import sys

import winhlp.__main__ as cli


class FakeHelpFile:
    def __init__(self, filepath):
        self.filepath = filepath

    def model_dump(self):
        return {"filepath": self.filepath, "raw_data": {"bytes": b"raw"}}


def test_bare_command_launches_tui(monkeypatch, tmp_path):
    source = tmp_path / "test.hlp"
    source.write_bytes(b"test")
    launched = []
    monkeypatch.setattr(cli, "HelpFile", FakeHelpFile)
    monkeypatch.setattr("winhlp.tui.run_tui", launched.append)
    monkeypatch.setattr(sys, "argv", ["winhlp", str(source)])

    assert cli.main() == 0
    assert len(launched) == 1
    assert launched[0].filepath == str(source)


def test_json_is_explicit_and_clean_by_default(monkeypatch, tmp_path, capsys):
    source = tmp_path / "test.hlp"
    source.write_bytes(b"test")
    monkeypatch.setattr(cli, "HelpFile", FakeHelpFile)
    monkeypatch.setattr(sys, "argv", ["winhlp", str(source), "--json"])

    assert cli.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {"filepath": str(source)}


def test_raw_implies_json(monkeypatch, tmp_path, capsys):
    source = tmp_path / "test.hlp"
    source.write_bytes(b"test")
    monkeypatch.setattr(cli, "HelpFile", FakeHelpFile)
    monkeypatch.setattr(sys, "argv", ["winhlp", str(source), "--raw"])

    assert cli.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["raw_data"]["bytes"] == "cmF3"
