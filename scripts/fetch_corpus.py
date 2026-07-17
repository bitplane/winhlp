#!/usr/bin/env python3
"""Fetch a help-file corpus from discmaster.textfiles.com into tests/data/corpus/.

Each search-download endpoint 302-redirects to a .tar.gz of matching files.
Downloads are done in series (be polite) and each is extracted into its own
subdirectory so numbered dirs inside different tarballs can't collide.

Usage:
  ./scripts/fetch_corpus.py 4 5 6 7          # HLP search pages 4-7 -> page<N>/
  ./scripts/fetch_corpus.py --query mvb      # q=mvb search -> query-mvb/
  ./scripts/fetch_corpus.py --clear 4 5 6 7  # wipe corpus first, then download
  ./scripts/fetch_corpus.py --clear          # just wipe the corpus and exit

The corpus dir is gitignored; it is raw input for scripts/collect_test_files.py.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PAGE_URL = "https://discmaster.textfiles.com/search?download=true&format=hlp&limit=1000&pageNum={n}"
QUERY_URL = "https://discmaster.textfiles.com/search?download=true&q={q}"
CORPUS = Path(__file__).resolve().parent.parent / "tests" / "data" / "corpus"
# Some discmaster endpoints 418 without a browser-like User-Agent.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def clear_corpus() -> None:
    if CORPUS.exists():
        shutil.rmtree(CORPUS)
    CORPUS.mkdir(parents=True, exist_ok=True)
    print(f"cleared {CORPUS}")


def _download_and_extract(url: str, dest: Path, label: str) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)
    try:
        print(f"{label}: downloading {url}")
        subprocess.run(
            ["curl", "-sSL", "--fail", "--retry", "3", "--max-time", "900", "-A", UA, "-o", tmp_path, url],
            check=True,
        )
        size = os.path.getsize(tmp_path)
        if size == 0:
            raise RuntimeError(f"{label}: downloaded 0 bytes")
        print(f"{label}: {size:,} bytes; extracting -> {dest}")
        subprocess.run(["tar", "xzf", tmp_path, "-C", str(dest)], check=True)
        n = sum(1 for p in dest.rglob("*") if p.suffix.lower() in (".hlp", ".mvb"))
        print(f"{label}: done, {n} help files")
    finally:
        os.unlink(tmp_path)


def fetch_page(n: int) -> None:
    _download_and_extract(PAGE_URL.format(n=n), CORPUS / f"page{n}", f"page {n}")


def fetch_query(q: str) -> None:
    _download_and_extract(QUERY_URL.format(q=q), CORPUS / f"query-{q}", f"query {q!r}")


def main() -> int:
    args = sys.argv[1:]
    if "--clear" in args:
        args.remove("--clear")
        clear_corpus()

    queries = []
    while "--query" in args:
        i = args.index("--query")
        if i + 1 >= len(args):
            print(__doc__)
            return 1
        queries.append(args[i + 1])
        del args[i : i + 2]

    try:
        pages = [int(a) for a in args]
    except ValueError:
        print(__doc__)
        return 1

    for q in queries:  # series
        fetch_query(q)
    for n in pages:  # series
        fetch_page(n)

    if pages or queries:
        total = sum(1 for p in CORPUS.rglob("*") if p.suffix.lower() in (".hlp", ".mvb"))
        print(f"\ncorpus now holds {total} help files across {CORPUS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
