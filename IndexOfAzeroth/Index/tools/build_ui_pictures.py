# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import pictures
from game import installed_version


def main():
    build = installed_version()
    unknown = [name for name in pictures.UI_PICTURES if not pictures.ui_picture(name, build)]
    pictures.flush()
    print(f"{len(pictures.UI_PICTURES) - len(unknown)} interface pictures in place for build {build}"
          + (f", {len(unknown)} the listfile doesn't know: {', '.join(unknown)}" if unknown else ""))


if __name__ == "__main__":
    import builder
    builder.run(main)
