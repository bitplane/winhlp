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


def main():
    parser = argparse.ArgumentParser(description="Dump HLP file structure to JSON.")
    parser.add_argument("hlp_filepath", help="Path to the HLP file.")
    args = parser.parse_args()

    if not os.path.exists(args.hlp_filepath):
        print(f"Error: File not found at {args.hlp_filepath}")
        return

    try:
        hlp_file = HelpFile(filepath=args.hlp_filepath)
        # Use the custom encoder for serialization
        print(json.dumps(hlp_file.model_dump(), indent=2, cls=BytesEncoder))
        return 0
    except Exception as e:
        print(f"Error parsing HLP file: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
