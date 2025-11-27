# A fork of CondaRTS

## Visual debug mode

Aids development/debugging. When running from a clone copy of source code,
edit `\src\constants.py` and change `VIEW_DEBUG_MODE_IS_ENABLED = False` to `True`.

- Turns off fog-of-war
- For each sprite:
  - adds magenta outline around bounding rectangle (corresponds to `.rect` attribute)
  - adds small magenta circle at location of `.position` attribute 
