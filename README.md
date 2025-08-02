# winhlp

Windows HLP file library for Python

Based on helpdeco by Manfred Winterhoff, Ben Collver + Paul Wise

## TODO

   2. External Jump Commands (`0xEA`, `0xEB`, `0xEE`, `0xEF`):
       * C Version: Fully parses and handles these commands, which refer to jumps to topics in external help files or
         secondary windows. It stores these as external references.
       * Python Version: These commands are explicitly marked with "skip for now" comments in
         _parse_formatting_commands within topic.py. This indicates a significant missing feature, meaning external
         links will not be correctly processed or extracted.
   3. Embedded Bitmaps within Topics:
       * C Version: Extracts the actual bitmap data for embedded images (bmc, bml, bmr commands) within topic content.
       * Python Version: While BitmapFile exists, the _parse_topic_content_interleaved function in topic.py only
         extracts metadata for embedded bitmaps and "skips picture data for now." The actual image data is not fully
         processed or made available within the parsed topic content.
   4. Context ID Reverse Hashing (`reverse_hash`):
       * C Version: The unhash function in helpdeco.c is a robust implementation for reconstructing context IDs from
         hash values, even attempting to derive human-readable names.
       * Python Version: The ContextFile.reverse_hash in src/winhlp/lib/internal_files/context.py is a simplified
         "best effort" attempt. It may not always produce the same or as accurate results as the C version,
         especially for complex or non-standard context IDs.
   5. `Derive` Functionality (Context ID Guessing):
       * C Version: The helpdeco tool includes a Derive function that attempts to guess context IDs from topic
         titles, making it more resilient to malformed help files or those with non-standard context ID generation.
       * Python Version: This "guessing" functionality is not present, which could lead to more "unresolved jump"
         errors when parsing certain help files.
   6. Full RTF Output:
       * C Version: The helpdeco tool is designed to output a comprehensive and accurate RTF representation of the
         help file content, including all formatting and structural elements.
       * Python Version: The ParsedTopic.get_rtf_content is a high-level RTF generator. While it handles basic
         formatting and tables, it's likely less comprehensive and accurate in its RTF reconstruction compared to the
         C tool, which aims for full fidelity.

