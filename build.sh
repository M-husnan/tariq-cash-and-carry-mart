#!/usr/bin/env bash
set -euo pipefail
python -m pip install -r requirements.txt
python backend/manage.py migrate --noinput
python backend/manage.py collectstatic --noinput

