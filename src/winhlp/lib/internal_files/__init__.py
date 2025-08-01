"""
winhlp.lib.internal_files - Internal file parsers

Parsers for the various internal files within HLP files.
"""

from .base import InternalFile
from .system import SystemFile
from .font import FontFile
from .topic import TopicFile
from .context import ContextFile
from .phrase import PhraseFile

__all__ = [
    "InternalFile",
    "SystemFile",
    "FontFile",
    "TopicFile",
    "ContextFile",
    "PhraseFile",
]
