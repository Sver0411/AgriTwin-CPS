"""Normalize declared quality-audited segments; keep the downloaded originals unchanged."""

import argparse
from pathlib import Path

from agritwin_cps.data_io.public_data import prepare_south_africa

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    audit = prepare_south_africa(args.source_dir, args.output)
    print(audit["segments"])
