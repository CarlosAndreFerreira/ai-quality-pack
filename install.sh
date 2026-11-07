#!/usr/bin/env sh
# Thin wrapper; the installer is install.py (cross-platform). On Windows: py install.py project .
exec python3 "$(dirname "$0")/install.py" "$@"
