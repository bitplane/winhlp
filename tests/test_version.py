"""Package version follows installed distribution metadata."""

from importlib.metadata import version

import winhlp


def test_package_version_matches_distribution():
    assert winhlp.__version__ == version("winhlp")
