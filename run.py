#!/usr/bin/env python3
"""Entry wrapper — jalanin bot.main sebagai module biar relative import jalan."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.main import main

if __name__ == "__main__":
    main()
