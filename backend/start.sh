#!/bin/sh
set -eu
cd "$(dirname "$0")"

# The free service has no separate pre-deploy process. Never reset existing data.
python manage.py migrate --noinput
python manage.py check --fail-level ERROR
exec python supervisor.py
