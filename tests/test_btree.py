"""Regression tests for malformed B-tree leaf chains."""

import struct
from itertools import islice

import pytest

from winhlp.lib.btree import BTree
from winhlp.lib.exceptions import BTreeError


def make_tree(next_pages):
    header = struct.pack("<HHH16shhhhhhi", 0x293B, 2, 8, b"", 0, 0, 0, -1, len(next_pages), 1, len(next_pages))
    pages = b"".join(struct.pack("<hhhh", 0, 1, index - 1, following) for index, following in enumerate(next_pages))
    return BTree(header + pages)


@pytest.mark.parametrize("next_pages", [[0], [1, 0], [1, 2, 1]])
def test_cyclic_leaf_chain_raises(next_pages):
    tree = make_tree(next_pages)
    # Bound iteration so a regression fails rather than hanging the test suite.
    with pytest.raises(BTreeError, match="Cycle in leaf pages"):
        list(islice(tree.iterate_leaf_pages(), len(next_pages) + 1))


@pytest.mark.parametrize("next_pages", [[-1], [1, 2, -1]])
def test_acyclic_leaf_chain_visits_each_page_once(next_pages):
    tree = make_tree(next_pages)
    assert list(tree.iterate_leaf_pages()) == [(page, 1) for page in tree.pages]
