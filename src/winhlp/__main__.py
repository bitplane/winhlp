import argparse
import json
import os
import sys
import base64
from winhlp.lib.hlp import HelpFile


class BytesEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode("ascii")
        return json.JSONEncoder.default(self, obj)


def strip_raw_data(obj):
    """Recursively drop 'raw_data' keys so the default JSON is readable.

    Every parsed structure stores a raw_data blob (the source bytes plus a copy
    of the parsed fields), which duplicates the model 2-3x and dominates the
    output. --raw keeps it for byte-level fidelity; by default we remove it.
    """
    if isinstance(obj, dict):
        return {k: strip_raw_data(v) for k, v in obj.items() if k != "raw_data"}
    if isinstance(obj, list):
        return [strip_raw_data(v) for v in obj]
    return obj


def main():
    parser = argparse.ArgumentParser(description="Parse a Windows HLP/MVB file to JSON or HTML.")
    parser.add_argument("hlp_filepath", help="Path to the HLP file.")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Include raw_data byte blobs (base64) for full byte-level fidelity.",
    )
    parser.add_argument(
        "--html",
        metavar="OUT.html",
        help="Render the whole help file to a single HTML file instead of JSON.",
    )
    parser.add_argument(
        "--images",
        choices=("embed", "extract"),
        default="embed",
        help="--html only: embed images as data URIs (default) or extract them to a folder.",
    )
    args = parser.parse_args()

    if not os.path.exists(args.hlp_filepath):
        print(f"Error: File not found at {args.hlp_filepath}")
        return 1

    try:
        hlp_file = HelpFile(filepath=args.hlp_filepath)
        if args.html:
            from winhlp.lib.html import export_html

            image_dir = os.path.splitext(args.html)[0] + "_images" if args.images == "extract" else None
            html_out = export_html(hlp_file, images=args.images, image_dir=image_dir)
            with open(args.html, "w", encoding="utf-8") as fh:
                fh.write(html_out)
            print(f"Wrote {args.html} ({len(html_out):,} bytes)")
            return 0
        data = hlp_file.model_dump()
        if not args.raw:
            data = strip_raw_data(data)
        print(json.dumps(data, indent=2, cls=BytesEncoder))
        return 0
    except Exception as e:
        print(f"Error parsing HLP file: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
