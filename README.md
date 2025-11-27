## Visual debug mode

Aids development/debugging. When running from a clone copy of source code,
edit `\src\constants.py` and change `VIEW_DEBUG_MODE_IS_ENABLED = False` to `True`.

For each sprite, adds:
- magenta outline around bounding rectangle (corresponds to `.rect` attribute)
- small magenta circle at location of `.position` attribute 
