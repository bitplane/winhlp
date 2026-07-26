"""Presentation-neutral division of topic content into fixed and scrolling regions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .internal_files.topic import ParsedTopic, TopicContentBlock


@dataclass(frozen=True)
class TopicLayout:
    fixed_blocks: tuple["TopicContentBlock", ...]
    scrolling_blocks: tuple["TopicContentBlock", ...]


def layout_topic(topic: "ParsedTopic") -> TopicLayout:
    """Split blocks at the exact TOPICOFFSET recorded while parsing."""
    boundary = topic.non_scroll_offset
    if boundary is None or topic.topic_offset is None or boundary <= topic.topic_offset:
        return TopicLayout((), tuple(topic.content_blocks))
    fixed = []
    scrolling = []
    for block in topic.content_blocks:
        start = getattr(block, "source_record_offset", None)
        if start is None:
            # Compatibility for callers constructing presentation models
            # directly rather than through the TOPIC parser.
            start = getattr(block, "source_offset", None)
        if start is not None and start < boundary:
            fixed.append(block)
        else:
            scrolling.append(block)
    return TopicLayout(tuple(fixed), tuple(scrolling))
