#! /usr/bin/env bash

set -e
set -x

# Let the DB start
python app/scripts/backend_pre_start.py

# Run migrations
alembic upgrade head

# Create initial data in DB
python app/scripts/initial_data.py

# Let browsers read signed links from the bucket (nothing to do on Postgres)
python -m app.scripts.setup_bucket
