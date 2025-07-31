"""Custom exceptions for the HLP file reader library."""


class HLPError(Exception):
    """Base class for exceptions in this module."""

    pass


class InvalidHLPFileError(HLPError):
    """Raised when the file is not a valid HLP file."""

    pass


class BTreeError(HLPError):
    """Raised for errors related to B-Tree parsing."""

    pass
