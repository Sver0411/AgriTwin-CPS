"""Run one simulation using the installed package CLI."""

import sys

from agritwin_cps.cli import main

if __name__ == "__main__":
    main(["simulate", *sys.argv[1:]])
