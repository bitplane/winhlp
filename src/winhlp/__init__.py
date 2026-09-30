"""
winhlp - Windows HLP file library for Python

A pure Python library for parsing Windows Help (.HLP) files.
Based on helpdeco by Manfred Winterhoff, Ben Collver + Paul Wise.
"""

from .lib.hlp import HelpFile
from .lib.exceptions import HLPError, InvalidHLPFileError, BTreeError
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("winhlp")
except PackageNotFoundError:
    __version__ = "0+unknown"
__author__ = "Gareth Davidson"
__email__ = "gaz@bitplane.net"

__all__ = [
    "HelpFile",
    "HLPError",
    "InvalidHLPFileError",
    "BTreeError",
]
