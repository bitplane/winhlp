"""Persistence tests for bookmarks and editable user notes."""

import json
from types import SimpleNamespace

from winhlp.lib.user_state import UserState


def test_user_state_round_trips_unicode_notes_and_bookmarks(tmp_path):
    help_path = tmp_path / "manual.hlp"
    topic = SimpleNamespace(topic_offset=42, title="A topic", context_names=["CTX_TOPIC"])
    state = UserState.for_help_file(help_path)

    assert state.toggle_bookmark(topic)
    state.set_note(42, "Remember café and 日本語")
    state.save()

    loaded = UserState.for_help_file(help_path)
    assert loaded.bookmarks[42].title == "A topic"
    assert loaded.bookmarks[42].context_name == "CTX_TOPIC"
    assert loaded.notes == {42: "Remember café and 日本語"}
    assert not loaded.diagnostic
    assert loaded.path == tmp_path / "manual.hlp.user.json"


def test_user_state_removes_empty_notes_and_toggles_bookmarks(tmp_path):
    topic = SimpleNamespace(topic_offset=7, title="Topic", context_names=[])
    state = UserState.for_help_file(tmp_path / "manual.hlp")
    state.set_note(7, "note")
    state.set_note(7, "  ")
    assert state.notes == {}
    assert state.toggle_bookmark(topic)
    assert not state.toggle_bookmark(topic)
    assert state.bookmarks == {}


def test_invalid_or_oversized_user_state_is_ignored_with_diagnostic(tmp_path):
    help_path = tmp_path / "manual.hlp"
    sidecar = tmp_path / "manual.hlp.user.json"
    sidecar.write_text("not json", encoding="utf-8")
    invalid = UserState.for_help_file(help_path)
    assert invalid.diagnostic
    assert not invalid.bookmarks and not invalid.notes

    sidecar.write_text(json.dumps({"version": 2}), encoding="utf-8")
    unsupported = UserState.for_help_file(help_path)
    assert "version" in unsupported.diagnostic

    sidecar.write_bytes(b" " * 1_000_001)
    oversized = UserState.for_help_file(help_path)
    assert "1 MB" in oversized.diagnostic
