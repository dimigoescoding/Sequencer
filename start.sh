#!/usr/bin/env bash
set -o errexit

python manage.py migrate --noinput
python manage.py ensure_admin

exec gunicorn sequencer.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers 1 \
  --threads 2 \
  --timeout 45 \
  --max-requests 500 \
  --max-requests-jitter 50
