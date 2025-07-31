"""Base class for internal file parsers."""

from pydantic import BaseModel


class InternalFile(BaseModel):
    """
    Base class for all internal file parsers.
    """

    filename: str
    raw_data: bytes
