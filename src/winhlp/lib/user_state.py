"""Persistent per-help-file bookmarks and editable user notes."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Bookmark:
    topic_offset: int
    title: str = ""
    context_name: str = ""


@dataclass
class UserState:
    """Small, portable sidecar stored beside the source help file."""

    path: Path
    bookmarks: dict[int, Bookmark] = field(default_factory=dict)
    notes: dict[int, str] = field(default_factory=dict)
    diagnostic: str = ""

    @classmethod
    def for_help_file(cls, help_path: str | Path) -> "UserState":
        path = Path(str(help_path) + ".user.json")
        state = cls(path)
        if not path.is_file():
            return state
        try:
            if path.stat().st_size > 1_000_000:
                raise ValueError("sidecar exceeds 1 MB")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("version") != 1:
                raise ValueError("unsupported sidecar version")
            for item in payload.get("bookmarks", ()):
                offset = int(item["topic_offset"])
                if offset >= 0:
                    state.bookmarks[offset] = Bookmark(
                        offset, str(item.get("title", "")), str(item.get("context_name", ""))
                    )
            for key, value in payload.get("notes", {}).items():
                offset = int(key)
                text = str(value)
                if offset >= 0 and text:
                    state.notes[offset] = text
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            state.diagnostic = f"{path.name}: {error}"
        return state

    def toggle_bookmark(self, topic) -> bool:
        offset = topic.topic_offset
        if offset is None:
            return False
        if offset in self.bookmarks:
            del self.bookmarks[offset]
            return False
        context = topic.context_names[0] if topic.context_names else ""
        self.bookmarks[offset] = Bookmark(offset, topic.title or "", context)
        return True

    def set_note(self, topic_offset: int, text: str) -> None:
        text = text.strip()
        if text:
            self.notes[topic_offset] = text
        else:
            self.notes.pop(topic_offset, None)

    def save(self) -> None:
        payload = {
            "version": 1,
            "bookmarks": [
                {
                    "topic_offset": bookmark.topic_offset,
                    "title": bookmark.title,
                    "context_name": bookmark.context_name,
                }
                for bookmark in sorted(self.bookmarks.values(), key=lambda item: item.topic_offset)
            ],
            "notes": {str(offset): text for offset, text in sorted(self.notes.items())},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
