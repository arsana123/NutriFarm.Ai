#!/usr/bin/env bash
# Build script for Render. Exit on the first error.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput

# Free Render services have no shell, so the admin user is created here from the
# DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD environment variables.
# It fails harmlessly when the user already exists or the variables are unset.
python manage.py createsuperuser --noinput || true
