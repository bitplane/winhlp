# winhlp

Windows HLP file library for Python

Based on helpdeco by Manfred Winterhoff, Ben Collver + Paul Wise

## TODO

   6. Full RTF Output:
       * C Version: The helpdeco tool is designed to output a comprehensive and accurate RTF representation of the
         help file content, including all formatting and structural elements.
       * Python Version: The ParsedTopic.get_rtf_content is a high-level RTF generator. While it handles basic
         formatting and tables, it's likely less comprehensive and accurate in its RTF reconstruction compared to the
         C tool, which aims for full fidelity.

Missing stuff:

   * `|TOMAP`: (Win 3.0 topic number to position mapping)
   * `|xWBTREE`, `|xWDATA`, `|xWMAP`: (Keyword B+ Trees for A-Z, a-z footnotes)
   * `|TTLBTREE`: (Topic Title B+ Tree)
   * `|CFn`: (Config macros for secondary windows)
   * `|Rose`: (Macros from [MACROS] section)
   * `|TopicId`: (ContextName assigned to topic offset)
   * `|Petra`: (RTF source file names)
   * `.GID` files and their internal structures (`|WinPos`, `|Pete`, `|Flags`, `|CntJump`, `|CntText`): (WinHlp32
     specific files)
   * `.GRP` files: (MediaView group files)
   * `.CAC`, `.AUX` files: (Auxiliary files)

