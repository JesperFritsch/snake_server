#!/bin/bash
source /home/jesper/snake_server/server_venv/bin/activate
umask 000
uvicorn main:app --host 0.0.0.0 --port 42069
deactivate
