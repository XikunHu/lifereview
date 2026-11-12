#!/usr/bin/env python3
"""Compatibility entry; same CLI and rules as the resumable runner."""
from run_deepseek_resumable import main

if __name__ == '__main__':
    raise SystemExit(main())
