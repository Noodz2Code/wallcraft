"""Entry point for ``python -m wallcraft`` and the PyInstaller build.

Uses an absolute import so it also works when PyInstaller runs this file as a script.
"""

import sys

from wallcraft.app import main

if __name__ == "__main__":
    sys.exit(main())
