#!/usr/bin/env python3
"""
Compare winhlp's extracted topic text with helpdeco's, file by file.

helpdeco (built from ref/) decompiles each help file to "lookalike" RTF
(``-r``), which is reduced to plain words and compared with the words of
winhlp's ``get_plain_text()`` for every topic. Markup, whitespace and titles
are ignored, so the score measures whether both tools recover the same text.

    scripts/compare_helpdeco.py tests/data                # summary
    scripts/compare_helpdeco.py tests/data/corpus --report out.json --show 5
"""

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_BINARY = REPO / "build" / "helpdeco"
HELP_SUFFIXES = {".hlp", ".mvb"}

# Destination groups whose text is not document text.
SKIP_DESTINATIONS = {"fonttbl", "colortbl", "stylesheet", "info", "footnote", "pict", "object", "fldinst"}
TOKEN = re.compile(rb"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\(.)|([{}])|([^\\{}\r\n]+)|[\r\n]+", re.S)


def build_helpdeco(target: Path) -> Path:
    """Compile helpdeco from ref/ (it predates modern C, hence the permissive flags)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    sources = [REPO / "ref" / name for name in ("helpdeco.c", "helpdec1.c", "compat.c")]
    flags = ["-std=gnu89", "-O1", "-w", "-fcommon", "-Wno-incompatible-pointer-types", "-Wno-int-conversion"]
    subprocess.run(["gcc", *flags, "-o", str(target), *map(str, sources)], check=True)
    return target


def rtf_topics(rtf: bytes) -> list[bytes]:
    """Reduce helpdeco RTF to the raw text of each topic (split on \\page)."""
    topics = [bytearray()]
    stack = []
    skip = False
    hidden = False
    for word, arg, hexbyte, symbol, brace, text in TOKEN.findall(rtf):
        if brace == b"{":
            stack.append((skip, hidden))
            continue
        if brace == b"}":
            if stack:
                skip, hidden = stack.pop()
            continue
        out = topics[-1]
        if word:
            name = word.decode()
            if name in SKIP_DESTINATIONS:
                skip = True
            elif name == "v":
                hidden = arg != b"0"
            elif name == "plain":
                hidden = False
            elif name == "page":
                topics.append(bytearray())
            elif not (skip or hidden):
                if name in ("par", "line"):
                    out += b"\n"
                elif name == "tab":
                    out += b"\t"
            continue
        if symbol == b"*":
            skip = True
            continue
        if skip or hidden:
            continue
        if hexbyte:
            out.append(int(hexbyte, 16))
        elif symbol in (b"{", b"}", b"\\"):
            out += symbol
        elif symbol == b"~":
            out += b" "
        elif symbol == b"_":
            out += b"-"
        elif text:
            out += text
    return [bytes(topic) for topic in topics]


def words(text: str) -> list[str]:
    # helpdeco writes bitmap references as literal {bmc name} text.
    text = re.sub(r"\{(?:bm|ew)[clr]\w*\s[^}]*\}", " ", text)
    return text.replace("\xa0", " ").split()


def compare_file(path: str, binary: str, timeout: int) -> dict:
    import logging
    import warnings

    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    from winhlp.lib.hlp import HelpFile

    result = {"file": path}
    try:
        helpfile = HelpFile(filepath=path)
    except Exception as error:
        return {**result, "status": "winhlp-error", "error": f"{type(error).__name__}: {error}"}
    encoding = helpfile.system.encoding if helpfile.system else "cp1252"
    ours = [topic.get_plain_text() for topic in (helpfile.topic.get_all_topics() if helpfile.topic else [])]

    with tempfile.TemporaryDirectory() as work:
        local = Path(work) / Path(path).name
        os.symlink(os.path.abspath(path), local)
        try:
            subprocess.run(
                [binary, local.name, "-r", "-y"],
                cwd=work,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {**result, "status": "helpdeco-timeout"}
        rtf_path = local.with_suffix(".rtf")
        if not rtf_path.exists():
            return {**result, "status": "helpdeco-error"}
        theirs = [topic.decode(encoding, errors="replace") for topic in rtf_topics(rtf_path.read_bytes())]

    a = words(" ".join(theirs))
    b = words(" ".join(ours))
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=len(a) + len(b) > 200_000)
    diffs = [
        {"op": op, "helpdeco": " ".join(a[i1:i2])[:200], "winhlp": " ".join(b[j1:j2])[:200]}
        for op, i1, i2, j1, j2 in matcher.get_opcodes()
        if op != "equal"
    ]
    return {
        **result,
        "status": "ok",
        "similarity": round(matcher.ratio(), 4) if a or b else 1.0,
        "helpdeco_topics": len(theirs),
        "winhlp_topics": len(ours),
        "helpdeco_words": len(a),
        "winhlp_words": len(b),
        "diffs": diffs[:20],
    }


def find_files(paths: list[str]) -> list[str]:
    found = []
    for item in paths:
        path = Path(item)
        if path.is_file():
            found.append(str(path))
        else:
            found.extend(str(p) for p in sorted(path.rglob("*")) if p.suffix.lower() in HELP_SUFFIXES)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="help files or directories to scan")
    parser.add_argument("--helpdeco", type=Path, default=DEFAULT_BINARY, help="helpdeco binary (built if missing)")
    parser.add_argument("--jobs", type=int, default=os.cpu_count())
    parser.add_argument("--timeout", type=int, default=120, help="seconds per helpdeco run")
    parser.add_argument("--threshold", type=float, default=0.99, help="similarity below this counts as a mismatch")
    parser.add_argument("--report", type=Path, help="write per-file results as JSON")
    parser.add_argument("--show", type=int, default=10, help="print diffs for the N worst files")
    args = parser.parse_args()

    if not args.helpdeco.exists():
        if not shutil.which("gcc"):
            print("gcc is needed to build helpdeco from ref/", file=sys.stderr)
            return 2
        build_helpdeco(args.helpdeco)

    files = find_files(args.paths)
    with ProcessPoolExecutor(args.jobs) as pool:
        results = list(
            pool.map(compare_file, files, [str(args.helpdeco)] * len(files), [args.timeout] * len(files), chunksize=2)
        )

    compared = [r for r in results if r["status"] == "ok"]
    mismatched = sorted((r for r in compared if r["similarity"] < args.threshold), key=lambda r: r["similarity"])
    total_a = sum(r["helpdeco_words"] for r in compared)
    total_b = sum(r["winhlp_words"] for r in compared)
    weighted = sum(r["similarity"] * (r["helpdeco_words"] + r["winhlp_words"]) for r in compared)

    print(f"{len(files)} files, {len(compared)} compared")
    for status in sorted({r["status"] for r in results} - {"ok"}):
        print(f"  {status}: {sum(r['status'] == status for r in results)}")
    if compared:
        print(f"  word-weighted similarity: {weighted / max(total_a + total_b, 1):.4f}")
        print(f"  words: helpdeco {total_a:,}, winhlp {total_b:,}")
        print(f"  files below {args.threshold}: {len(mismatched)}")
    for r in mismatched[: args.show]:
        print(f"\n{r['file']}  similarity={r['similarity']}  topics {r['helpdeco_topics']}/{r['winhlp_topics']}")
        for diff in r["diffs"][:5]:
            print(f"  {diff['op']:8} helpdeco: {diff['helpdeco'][:90]!r}")
            print(f"  {'':8} winhlp:   {diff['winhlp'][:90]!r}")

    if args.report:
        args.report.write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
