"""
FILE: src/__main__.py
WHY: Lets a reviewer run the app with `python -m src` instead of remembering
     the CLI module name.
"""

from src.cli import main

if __name__ == "__main__":
    main()
