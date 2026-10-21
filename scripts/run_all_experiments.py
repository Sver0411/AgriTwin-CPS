"""Run all seven predeclared experiment groups."""

import sys

from agritwin_cps.cli import main

if __name__ == "__main__":
    main(["all", *sys.argv[1:]])
