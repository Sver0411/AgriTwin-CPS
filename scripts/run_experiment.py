"""Run a paired multi-seed experiment."""

import sys

from agritwin_cps.cli import main

if __name__ == "__main__":
    main(["experiment", *sys.argv[1:]])
