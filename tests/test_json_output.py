"""Tests for the JSON dump: clean by default, raw behind --raw, round-trips."""

import glob
import json
import os

import pytest
from winhlp.lib.hlp import HelpFile
from winhlp.__main__ import strip_raw_data, BytesEncoder

DATA = os.path.join(os.path.dirname(__file__), "data")
# Exclude the raw corpus/ tree (collector input); test the curated files only.
HLP_FILES = sorted(
    f for f in glob.glob(os.path.join(DATA, "**", "*.HLP"), recursive=True) if os.sep + "corpus" + os.sep not in f
)


def _has_key(obj, key):
    if isinstance(obj, dict):
        return key in obj or any(_has_key(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_key(v, key) for v in obj)
    return False


@pytest.mark.parametrize("path", HLP_FILES, ids=[os.path.basename(p) for p in HLP_FILES])
def test_json_roundtrips_clean_and_raw(path):
    hlp = HelpFile(filepath=path)
    full = hlp.model_dump()

    # Raw dump keeps raw_data and must serialize to JSON.
    json.dumps(full, cls=BytesEncoder)
    assert _has_key(full, "raw_data")

    # Clean dump drops every raw_data blob and must still serialize.
    clean = strip_raw_data(full)
    json.dumps(clean, cls=BytesEncoder)
    assert not _has_key(clean, "raw_data")


def test_clean_dump_is_smaller():
    hlp = HelpFile(filepath=os.path.join(DATA, "win311/SOL.HLP"))
    full = json.dumps(hlp.model_dump(), cls=BytesEncoder)
    clean = json.dumps(strip_raw_data(hlp.model_dump()), cls=BytesEncoder)
    assert len(clean) < len(full)
