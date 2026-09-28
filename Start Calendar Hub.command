#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'Python 3.10+ is required. See START-HERE.md for setup instructions.'
  read -r answer
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  printf '%s\n' 'Python 3.10+ is required. See START-HERE.md.'
  read -r answer
  exit 1
fi
python3 onboard.py start
result=$?
printf '\n%s\n' 'Press Return to close this window.'
read -r answer
exit "$result"
