#!/bin/bash
set -e

echo "Running alembic upgrade"
alembic upgrade head

echo "Running uvicorn"
uvicorn app.main:app --host 0.0.0.0 --port 8000
