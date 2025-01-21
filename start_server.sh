#!/bin/bash

# Default values
RELOAD=""

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -d|--dev) DEV="--dev"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

source /home/jesper/py_fun/snake_server/server_venv/bin/activate

umask 000
run-snake-server $DEV
deactivate
