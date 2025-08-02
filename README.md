# winhlp

Windows HLP file library for Python

Based on helpdeco by Manfred Winterhoff, Ben Collver + Paul Wise

## TODO / missing

   1. Missing Internal Files: A large number of internal file types are not implemented at all.
   2. `|SYSTEM` Divergences:
       * Missing FTINDEX and LANGUAGE record parsers.
       * Potentially incorrect WINDOW and DEFFONT parsing.
   3. `|FONT` Divergences:
       * Missing mvbfont and mvbstyle parsing.
       * Potentially brittle NewStyle parsing.
   4. `|TOPIC` Major Divergences:
       * Incorrect Parsing Strategy: The lack of interleaved parsing of LinkData1 and LinkData2 is the most critical
         flaw.
       * Incomplete Table Support: RecordType 0x23 is not fully implemented.
       * Potentially Flawed Compressed Integer Parsing: The compressed integer functions may not be fully correct.
       * Incomplete `TOPICOFFSET` Handling: The logic for TOPICOFFSET is likely incomplete.


