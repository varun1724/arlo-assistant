#!/bin/bash
set -e
exec gosu arlo uvicorn app.main:app --host 0.0.0.0 --port 8002
