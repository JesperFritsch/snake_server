#!/bin/bash

# Default values
RELOAD=""

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -d|--dev) RELOAD="--reload"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

if [[ "$(uname -s)" == *"CYGWIN"* || "$(uname -s)" == *"MINGW"* || "$(uname -s)" == *"MSYS"* ]]; then
  # Windows path
  source /b/pythonStuff/snake_server/server_venv/Scripts/activate
else
  # Unix-like system path
  source /home/jesper/snake_server/server_venv/bin/activate
fi

umask 000
uvicorn main:app --host 0.0.0.0 --port 42069 $RELOAD
deactivate