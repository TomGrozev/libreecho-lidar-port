#!/usr/bin/env python3
"""Entry point for the Lidar boot-chain restore tool. See README.md."""

import sys

from lidarrestore.cli import main

if __name__ == "__main__":
    sys.exit(main())
