"""Presentation-neutral topic indexing, navigation, and link resolution."""

from __future__ import annotations

import bisect
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, TYPE_CHECKING

from .internal_files.context import ContextFile
from .internal_files.topic import HotspotMapping, ParsedTopic

if TYPE_CHECKING:
    from .hlp import HelpFile


TargetKind = Literal["topic", "popup", "choice", "macro", "external", "unresolved"]


@dataclass(frozen=True)
class ResolvedTarget:
    """The result of interpreting a WinHelp hotspot target."""

    kind: TargetKind
    original: str
    topic: Optional[ParsedTopic] = None
    detail: Optional[str] = None
    open_as_popup: bool = False
    topics: tuple[ParsedTopic, ...] = ()
    document: Optional[object] = None

    @property
    def navigable(self) -> bool:
        return (self.kind in ("topic", "popup") and self.topic is not None) or (
            self.kind == "choice" and bool(self.topics)
        )


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
    kind: str = "topic"
    topics: tuple[ParsedTopic, ...] = ()
    target: str = ""
    source: str = ""
    keyword_type: str = ""
    macro: str = ""
    index_title: str = ""


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
        self.cnt = self._load_cnt()
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
        system = getattr(self.helpfile, "system", None)
        if system is not None:
            for record in system.records:
                if isinstance(record, dict) and record.get("type") == "CONTENTS":
                    topic = self.topic_for_offset(record.get("contents_offset"))
                    if topic is not None:
                        return topic
        return self.topics[0] if self.topics else None

    def _load_cnt(self):
        system = getattr(self.helpfile, "system", None)
        filename = getattr(system, "cnt_filename", None)
        if not filename:
            return None
        from .cnt import load_cnt

        sibling = Path(self.helpfile.filepath).resolve().parent / Path(filename.replace("\\", "/")).name
        if not sibling.is_file():
            return None
        return load_cnt(sibling, getattr(system, "encoding", "cp1252"))

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

    @property
    def has_authored_contents(self) -> bool:
        """Whether a CNT/GID source supplies a curated Contents hierarchy."""
        return bool(
            (self.cnt and self.cnt.entries)
            or (getattr(self.helpfile, "cnttext", None) and getattr(self.helpfile.cnttext, "topic_titles", None))
        )

    def contents_entries(self) -> list[NavigationEntry]:
        if self.cnt and self.cnt.entries:
            entries = []
            for item in self.cnt.entries:
                topic = self._resolve_cnt_reference(item.reference)
                entries.append(
                    NavigationEntry(
                        item.label,
                        topic,
                        item.level,
                        item.kind,
                        (topic,) if topic else (),
                        item.reference,
                        "CNT",
                    )
                )
            return entries
        cnttext = getattr(self.helpfile, "cnttext", None)
        if cnttext and cnttext.topic_titles:
            jumps = getattr(getattr(self.helpfile, "cntjump", None), "jump_references", [])
            entries = []
            for index, title in enumerate(cnttext.topic_titles):
                reference = str(jumps[index]) if index < len(jumps) else ""
                topic = self.topic_by_context_name(reference) or self.topic_by_context_name(title)
                level = (len(title) - len(title.lstrip("\t"))) + (len(title) - len(title.lstrip(" "))) // 2
                entries.append(
                    NavigationEntry(
                        title.lstrip(),
                        topic,
                        level,
                        "topic" if topic else "unresolved",
                        (topic,) if topic else (),
                        reference,
                        "GID",
                    )
                )
            return entries
        catalog = getattr(self.helpfile, "catalog", None)
        if catalog and catalog.topic_offsets:
            topics = [self.topic_for_offset(offset) for offset in catalog.topic_offsets]
            return [
                NavigationEntry(
                    topic.title or f"Topic {index + 1}",
                    topic,
                    kind="sequence",
                    topics=(topic,),
                    source="CATALOG",
                )
                for index, topic in enumerate(topics)
                if topic is not None
            ]
        return [NavigationEntry(topic.title or f"Topic {index + 1}", topic) for index, topic in enumerate(self.topics)]

    def index_entries(self) -> list[NavigationEntry]:
        entries = {}
        if self.cnt:
            for title, target in self.cnt.indices:
                key = ("CNT", title.casefold(), target.casefold())
                entries[key] = NavigationEntry(
                    title or target,
                    None,
                    kind="unresolved",
                    target=target,
                    source="CNT",
                    index_title=title,
                )
        for source_name, sources in (
            ("search", getattr(self.helpfile, "keyword_search_files", {})),
            ("index", getattr(self.helpfile, "keyword_index_files", {})),
        ):
            for keyword_type, files in sources.items():
                index_title = getattr(getattr(self.helpfile, "system", None), "keyword_index_titles", {}).get(
                    keyword_type, ""
                )
                btree = files.get("btree")
                data = files.get("data")
                if not btree:
                    continue
                for keyword, record in btree.keyword_map.items():
                    topics = []
                    macro = ""
                    if getattr(btree, "is_gid_format", False):
                        offsets = [item.get("topic_offset") for item in getattr(record, "records", [])]
                    elif data is not None:
                        offsets = data.get_topic_offsets_range(
                            getattr(record, "kw_data_offset", 0), getattr(record, "count", 0)
                        )
                    else:
                        offsets = []
                    for offset in offsets:
                        if offset == -1:
                            macro_entry = getattr(self.helpfile, "rose", None)
                            if macro_entry:
                                found = macro_entry.get_macro_by_hash(ContextFile.calculate_hash(keyword))
                                macro = found.macro if found else macro
                            continue
                        topic = self.topic_for_offset(offset)
                        if topic is not None and topic not in topics:
                            topics.append(topic)
                    parent, separator, child = keyword.partition(",")
                    label = child.strip() if separator and child.strip() else parent.strip() if separator else keyword
                    level = 1 if separator else 0
                    key = (keyword_type, keyword.casefold(), source_name)
                    entries[key] = NavigationEntry(
                        label,
                        topics[0] if len(topics) == 1 else None,
                        level,
                        "macro" if macro and not topics else "keyword",
                        tuple(topics),
                        keyword,
                        source_name,
                        keyword_type,
                        macro,
                        index_title,
                    )
                    if separator:
                        parent_key = (keyword_type, parent.casefold(), source_name)
                        entries.setdefault(
                            parent_key,
                            NavigationEntry(
                                parent.strip(),
                                None,
                                0,
                                "heading",
                                target=parent.strip(),
                                source=source_name,
                                keyword_type=keyword_type,
                                index_title=index_title,
                            ),
                        )
        if not entries:
            for topic in self.topics:
                for keyword in topic.keywords:
                    key = ("derived", keyword.casefold(), "topic")
                    previous = entries.get(key)
                    topics = (*previous.topics, topic) if previous and topic not in previous.topics else (topic,)
                    entries[key] = NavigationEntry(
                        keyword,
                        topics[0] if len(topics) == 1 else None,
                        topics=topics,
                        source="derived",
                    )
        return sorted(
            entries.values(),
            key=lambda entry: (entry.keyword_type, (entry.target or entry.label).casefold(), entry.level),
        )

    def _resolve_cnt_reference(self, reference: str) -> Optional[ParsedTopic]:
        if not reference:
            return None
        local = reference.partition("@")[0].partition(">")[0].strip()
        if local.startswith("!"):
            return None
        topic = self.topic_by_context_name(local)
        if topic is not None:
            return topic
        try:
            return self.topic_for_offset(int(local, 0))
        except ValueError:
            return None

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
                document=self,
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

    def resolve_bitmap_hotspot(self, hotspot) -> ResolvedTarget:
        """Resolve a typed SHG/MRB hotspot without executing arbitrary macros."""
        kind = hotspot.hotspot_type
        if kind == "macro":
            return self.resolve_target(f"macro:{hotspot.target}")
        if kind in ("external_jump", "external_popup"):
            context, window, filename = _split_external_reference(hotspot.target)
            fields = []
            if context:
                fields.append(f"context_name:{context}")
            if window:
                fields.append(f"window:{window}")
            if filename:
                fields.append(f"file:{filename}")
            return ResolvedTarget(
                "external",
                "|".join(fields) or hotspot.target,
                detail=f"Could not resolve external bitmap hotspot: {hotspot.target}",
                open_as_popup=kind == "external_popup",
                document=self,
            )
        if kind in ("topic", "popup"):
            topic = self.topic_by_context_name(hotspot.target) if hotspot.target else None
            if topic is None:
                return self.resolve_context_hash(hotspot.hash_value, popup=kind == "popup")
            return ResolvedTarget(kind, hotspot.target, topic=topic)
        return ResolvedTarget("unresolved", hotspot.target, detail=f"Unknown bitmap hotspot type 0x{hotspot.id0:02X}")

    def resolve_target(self, target: Optional[str]) -> ResolvedTarget:
        original = target or ""
        if not target:
            return ResolvedTarget("unresolved", original, detail="This hotspot has no target.")
        if target.startswith("macro:"):
            macro = target[len("macro:") :]
            return self._resolve_navigation_macro(macro, original)
        if target.startswith(("topic_offset:", "file:", "window:", "window_number:")):
            return ResolvedTarget(
                "external",
                original,
                detail=f"External WinHelp target is not supported: {target}",
                document=self,
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
        return ResolvedTarget(kind, original, topic=topic, document=self)

    def _resolve_navigation_macro(self, macro: str, original: str) -> ResolvedTarget:
        from .macros import parse_navigation_macro

        parsed = parse_navigation_macro(macro)
        if parsed is None:
            return ResolvedTarget(
                "macro", original, detail=f"WinHelp macro execution is not supported: {macro}", document=self
            )
        arguments = parsed.arguments
        if parsed.name in ("jumpid", "popupid") and arguments:
            filename = arguments[0] if len(arguments) > 1 else ""
            context = arguments[1] if len(arguments) > 1 else arguments[0]
            if not filename:
                topic = self.topic_by_context_name(context)
                if topic is not None:
                    return ResolvedTarget(
                        "popup" if parsed.name == "popupid" else "topic",
                        original,
                        topic=topic,
                        document=self,
                    )
            fields = [f"context_name:{context}"]
            if filename:
                fields.append(f"file:{filename}")
            return ResolvedTarget(
                "external",
                "|".join(fields),
                open_as_popup=parsed.name == "popupid",
                document=self,
            )
        if parsed.name == "jumpcontext" and arguments:
            filename = arguments[0] if len(arguments) > 1 else ""
            reference = arguments[1] if len(arguments) > 1 else arguments[0]
            fields = [f"topic_offset:{reference}"]
            if filename:
                fields.append(f"file:{filename}")
            return ResolvedTarget("external", "|".join(fields), document=self)
        if parsed.name in ("alink", "klink") and arguments:
            requested = {item.strip().casefold() for item in arguments[0].split(";") if item.strip()}
            topics = []
            for entry in self.index_entries():
                if entry.target.casefold() in requested or entry.label.casefold() in requested:
                    for topic in entry.topics or ((entry.topic,) if entry.topic else ()):
                        if topic not in topics:
                            topics.append(topic)
            if len(topics) == 1:
                return ResolvedTarget("topic", original, topic=topics[0], document=self)
            if topics:
                return ResolvedTarget("choice", original, topics=tuple(topics), document=self)
            return ResolvedTarget("unresolved", original, detail=f"No topics matched {macro}", document=self)
        return ResolvedTarget("macro", original, detail=f"Unsupported navigation macro form: {macro}", document=self)

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


def _split_external_reference(reference: str) -> tuple[str, str, str]:
    """Split the WinHelp ``Context>Window@File`` external-reference syntax."""
    local, at, filename = reference.partition("@")
    context, separator, window = local.partition(">")
    return context, window if separator else "", filename if at else ""
