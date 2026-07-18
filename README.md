# winhlp

A pure-Python parser for Windows Help (`.hlp`) and MediaView (`.mvb`) files —
the help format used from Windows 3.0 through Windows 95 before everything
went all chmmy. It parses a help file into a structured object model and
can export it to JSON or a single browsable HTML page.

Based on helpdeco by Manfred Winterhoff, Ben Collver, and Paul Wise, therefore
GPL licensed.

* [🏠 home](https://bitplane.net/dev/python/winhlp)
  * [📖 helpfile](https://bitplane.net/dev/python/winhlp/helpfile)
* [😺 src](https://github.com/bitplane/winhlp)
* [🐍 pypi](https://pypi.org/project/winhlp)

## Install

```sh
pip install winhlp          # core (JSON)
pip install winhlp[html]    # + Pillow, for PNG images in HTML export
```

## Command line

```sh
winhlp file.hlp                        # dump the parsed structure as JSON
winhlp file.hlp --raw                  # include raw byte blobs (base64)
winhlp file.hlp --html out.html        # render the whole file to one HTML page
winhlp file.hlp --html out.html --images extract   # write images to out_images/
```

The HTML export is a single self-contained page: a table of contents followed by
every topic as an anchored section, with internal jumps/popups turned into
in-page links, character formatting from the `|FONT` descriptors as CSS, and
images embedded as PNG data URIs (or extracted to a folder).

## Library

```python
from winhlp.lib.hlp import HelpFile

hlp = HelpFile(filepath="file.hlp")
for topic in hlp.topic.get_all_topics():
    print(topic.title, topic.context_names)
    print(topic.get_plain_text())

hlp.model_dump()          # full structured data (Pydantic)
hlp.parse_errors          # non-fatal per-file problems, if any

from winhlp.lib.html import export_html
open("out.html", "w").write(export_html(hlp))
```

## What it handles

- WinHelp 3.0, 3.1, and Windows 95, plus MediaView `.mvb` books.
- Topic text and formatting, tables, hotspots/jumps, bitmaps (`|bmN`, SHG/MRB,
  named MediaView resources), phrases (old-style and Hall compression),
  `|CONTEXT`/keyword/title cross-references, and context-id recovery.
- Malformed or truncated files degrade gracefully (see `parse_errors`) rather
  than aborting.

Parsing has been validated across ~6,500 real-world help files.

## Development

```sh
make dev       # set up the venv + pre-commit hooks
make test      # run the test suite
make coverage  # HTML coverage report in htmlcov/
```

## License

GPLv2, because that's what the original is.

As much as I dislike restrictive license terms, it'd be a lie to say this wasn't
derived from the source code of helpdeco.
