"""Presentation-neutral topic indexing, navigation, and link resolution."""

from __future__ import annotations

import bisect
import os
from dataclasses import dataclass
from typing import Literal, Optional, TYPE_CHECKING

from .internal_files.context import ContextFile
from .internal_files.topic import HotspotMapping, ParsedTopic

if TYPE_CHECKING:
    from .hlp import HelpFile


TargetKind = Literal["topic", "popup", "macro", "external", "unresolved"]


@dataclass(frozen=True)
class ResolvedTarget:
    """The result of interpreting a WinHelp hotspot target."""

    kind: TargetKind
    original: str
    topic: Optional[ParsedTopic] = None
    detail: Optional[str] = None
    open_as_popup: bool = False

    @property
    def navigable(self) -> bool:
        return self.kind in ("topic", "popup") and self.topic is not None


@dataclass(frozen=True)
class EmbeddedResource:
    """A normalized embedded bitmap or MediaView resource reference."""

    kind: str
    alignment: str
    reference: str
    resource_name: str


@dataclass(frozen=True)
class NavigationEntry:
    label: str
    topic: Optional[ParsedTopic]
    level: int = 0


def parse_embedded_resource(marker: str) -> Optional[EmbeddedResource]:
    """Normalize ``bitmap:align:n`` and ``window:align:EWC`` markers."""
    kind, separator, remainder = marker.partition(":")
    if not separator:
        return None
    alignment, separator, reference = remainder.partition(":")
    if not separator:
        return None
    if kind == "bitmap":
        resource_name = f"|bm{reference}" if reference.isdigit() else reference
    elif kind == "window":
        resource_name = reference.split(",")[-1].strip().lstrip("!").strip()
    else:
        resource_name = reference
    return EmbeddedResource(kind, alignment, reference, resource_name)


class HelpDocument:
    """Indexes a parsed :class:`HelpFile` for presentation consumers."""

    def __init__(self, helpfile: HelpFile):
        self.helpfile = helpfile
        self.topics = tuple(helpfile.get_topics())
        self._by_number = {topic.topic_number: topic for topic in self.topics if topic.topic_number is not None}
        self._by_offset = {topic.topic_offset: topic for topic in self.topics if topic.topic_offset is not None}
        self._offsets = sorted(self._by_offset)
        self._search_text = {
            id(topic): " ".join(
                [
                    topic.title or "",
                    *topic.context_names,
                    *topic.keywords,
                    topic.get_plain_text(),
                ]
            ).casefold()
            for topic in self.topics
        }

    @property
    def initial_topic(self) -> Optional[ParsedTopic]:
        return self.topics[0] if self.topics else None

    def topic_by_number(self, number: int) -> Optional[ParsedTopic]:
        return self._by_number.get(number)

    def topic_for_offset(self, offset: Optional[int]) -> Optional[ParsedTopic]:
        """Return the topic whose range contains an offset."""
        if offset is None:
            return None
        exact = self._by_offset.get(offset)
        if exact is not None:
            return exact
        index = bisect.bisect_right(self._offsets, offset) - 1
        return self._by_offset[self._offsets[index]] if index >= 0 else None

    def topic_by_context_name(self, name: str) -> Optional[ParsedTopic]:
        folded = name.casefold()
        for topic in self.topics:
            if any(context.casefold() == folded for context in topic.context_names):
                return topic

        topicid = getattr(self.helpfile, "topicid", None)
        if topicid is not None:
            for context_name, offset in topicid.context_topic_map.items():
                if context_name.casefold() == folded:
                    return self.topic_for_offset(offset)

        context = getattr(self.helpfile, "context", None)
        if context is None:
            return None
        hashed = ContextFile.calculate_hash(name)
        offset = self._context_offset(hashed)
        return self.topic_for_offset(offset)

    def search(self, query: str) -> list[ParsedTopic]:
        terms = query.casefold().split()
        if not terms:
            return list(self.topics)
        return [topic for topic in self.topics if all(term in self._search_text[id(topic)] for term in terms)]

    def contents_entries(self) -> list[NavigationEntry]:
        catalog = getattr(self.helpfile, "catalog", None)
        if catalog and catalog.topic_offsets:
            topics = [self.topic_for_offset(offset) for offset in catalog.topic_offsets]
            return [
                NavigationEntry(topic.title or f"Topic {index + 1}", topic)
                for index, topic in enumerate(topics)
                if topic is not None
            ]
        cnttext = getattr(self.helpfile, "cnttext", None)
        if cnttext and cnttext.topic_titles:
            jumps = getattr(getattr(self.helpfile, "cntjump", None), "jump_references", [])
            entries = []
            for index, title in enumerate(cnttext.topic_titles):
                reference = str(jumps[index]) if index < len(jumps) else ""
                topic = self.topic_by_context_name(reference) or self.topic_by_context_name(title)
                level = (len(title) - len(title.lstrip("\t"))) + (len(title) - len(title.lstrip(" "))) // 2
                entries.append(NavigationEntry(title.lstrip(), topic, level))
            return entries
        return [NavigationEntry(topic.title or f"Topic {index + 1}", topic) for index, topic in enumerate(self.topics)]

    def index_entries(self) -> list[NavigationEntry]:
        entries = []
        seen = set()
        for topic in self.topics:
            for keyword in topic.keywords:
                folded = keyword.casefold()
                key = (folded, id(topic))
                if key not in seen:
                    seen.add(key)
                    entries.append(NavigationEntry(keyword, topic))
        return sorted(entries, key=lambda entry: entry.label.casefold())

    def browse_previous(self, topic: ParsedTopic) -> Optional[ParsedTopic]:
        return self.topic_by_number(topic.browse_prev_topic) if topic.browse_prev_topic is not None else None

    def browse_next(self, topic: ParsedTopic) -> Optional[ParsedTopic]:
        return self.topic_by_number(topic.browse_next_topic) if topic.browse_next_topic is not None else None

    def resolve_hotspot(self, hotspot: HotspotMapping) -> ResolvedTarget:
        if hotspot.hotspot_type == "macro":
            return self.resolve_target(f"macro:{hotspot.target}")
        if hotspot.hotspot_type in ("external", "external_jump", "external_popup"):
            return ResolvedTarget(
                "external",
                hotspot.target,
                detail=f"External WinHelp target is not supported: {hotspot.target}",
                open_as_popup=hotspot.hotspot_type == "external_popup",
            )
        prefix = "popup" if hotspot.hotspot_type == "popup" else "topic"
        return self.resolve_target(f"{prefix}:{hotspot.target}")

    def resolve_context_hash(self, hash_value: int, popup: bool = False) -> ResolvedTarget:
        """Resolve a bitmap hotspot context hash."""
        offset = self._context_offset(hash_value)
        topic = self.topic_for_offset(offset)
        kind = "popup" if popup else "topic"
        original = f"{kind}:{hash_value & 0xFFFFFFFF:08X}"
        if topic is None:
            return ResolvedTarget("unresolved", original, detail=f"Could not resolve bitmap hotspot {original}")
        return ResolvedTarget(kind, original, topic=topic)

    def resolve_target(self, target: Optional[str]) -> ResolvedTarget:
        original = target or ""
        if not target:
            return ResolvedTarget("unresolved", original, detail="This hotspot has no target.")
        if target.startswith("macro:"):
            macro = target[len("macro:") :]
            return ResolvedTarget("macro", original, detail=f"WinHelp macro execution is not supported: {macro}")
        if target.startswith(("topic_offset:", "file:", "window:", "window_number:")):
            return ResolvedTarget(
                "external",
                original,
                detail=f"External WinHelp target is not supported: {target}",
            )

        kind, separator, reference = target.partition(":")
        if not separator or kind not in ("topic", "popup"):
            return ResolvedTarget("unresolved", original, detail=f"Unrecognized hotspot target: {target}")

        topic = None
        if reference.upper().startswith("TOPIC"):
            try:
                topic = self.topic_by_number(int(reference[5:]))
            except ValueError:
                topic = None
        else:
            try:
                value = int(reference, 16)
            except ValueError:
                value = None
            if value is not None:
                offset = self._context_offset(value)
                topic = self.topic_for_offset(offset) if offset is not None else self.topic_for_offset(value)

        if topic is None:
            return ResolvedTarget("unresolved", original, detail=f"Could not resolve hotspot target: {target}")
        return ResolvedTarget(kind, original, topic=topic)

    def _context_offset(self, hash_value: int) -> Optional[int]:
        context = getattr(self.helpfile, "context", None)
        if context is None:
            return None
        unsigned = hash_value & 0xFFFFFFFF
        signed = unsigned if unsigned < 0x80000000 else unsigned - 0x100000000
        return context.context_map.get(signed, context.context_map.get(unsigned))


class HelpNavigator:
    """UI-independent topic history for a :class:`HelpDocument`."""

    def __init__(self, document: HelpDocument, initial_topic: Optional[ParsedTopic] = None):
        self.document = document
        self.current = initial_topic if initial_topic is not None else document.initial_topic
        self.back_stack: list[ParsedTopic] = []
        self.forward_stack: list[ParsedTopic] = []

    def go_to(self, topic: Optional[ParsedTopic]) -> Optional[ParsedTopic]:
        if topic is None or topic is self.current:
            return self.current
        if self.current is not None:
            self.back_stack.append(self.current)
        self.current = topic
        self.forward_stack.clear()
        return self.current

    def back(self) -> Optional[ParsedTopic]:
        if not self.back_stack:
            return self.current
        if self.current is not None:
            self.forward_stack.append(self.current)
        self.current = self.back_stack.pop()
        return self.current

    def forward(self) -> Optional[ParsedTopic]:
        if not self.forward_stack:
            return self.current
        if self.current is not None:
            self.back_stack.append(self.current)
        self.current = self.forward_stack.pop()
        return self.current

    def browse_previous(self) -> Optional[ParsedTopic]:
        return self.go_to(self.document.browse_previous(self.current)) if self.current is not None else None

    def browse_next(self) -> Optional[ParsedTopic]:
        return self.go_to(self.document.browse_next(self.current)) if self.current is not None else None


def help_title(helpfile: HelpFile) -> str:
    system = getattr(helpfile, "system", None)
    return (system.title if system and system.title else None) or os.path.basename(helpfile.filepath)
