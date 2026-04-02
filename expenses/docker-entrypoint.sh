#!/bin/sh
set -e
# uvicorn принимает только lowercase; LOG_LEVEL из compose / .env может быть в любом регистре
LV=$(printf '%s' "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')
exec uvicorn main:app --host 0.0.0.0 --port 1242 --log-level "${LV}"
