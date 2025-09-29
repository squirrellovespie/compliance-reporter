#!/usr/bin/env bash
set -e
export PYTHONPATH=./src:$PYTHONPATH
uvicorn api.app:create_app --reload --host 0.0.0.0 --port 8000
