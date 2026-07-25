"""Regression tests for metadata-driven Windows code-page selection."""

import os

from winhlp.lib.hlp import HelpFile

DATA = os.path.join(os.path.dirname(__file__), "data")


def test_japanese_system_metadata_is_applied_before_text_decoding():
    hlp = HelpFile(filepath=os.path.join(DATA, "coverage", "mplayer_1.hlp"))

    assert hlp.system.encoding == "cp932"
    assert hlp.system.lcid == 0x0411
    assert hlp.system.charset == 0x0080
    assert hlp.system.title == "ﾒﾃﾞｨｱ ﾌﾟﾚｰﾔｰのﾍﾙﾌﾟ"


def test_japanese_hall_phrases_titles_and_keywords_use_system_encoding():
    hlp = HelpFile(filepath=os.path.join(DATA, "coverage", "mplayer_1.hlp"))
    topic = hlp.get_topics()[0]

    assert topic.title == "マルチメディア ファイルを再生するには"
    assert "[デバイス] メニューで、ファイルを再生するデバイス" in topic.get_plain_text()
    assert "K:[リンク貼り付け] コマンド" in topic.keywords
