#!/bin/bash
# One-container start for Render's free tier: health page + scheduler + bot.
# If any of them dies the container exits and Render restarts it. docker compose doesn't use this.

# Render sends SIGTERM on a redeploy: stop every child, so the old bot quits polling promptly
# instead of fighting the new one over the same token.
trap 'trap - TERM INT; kill 0' TERM INT

# Build the tables once, up front. Two processes creating them at the same moment can
# collide on Postgres; after this, their own init_db() finds everything already there.
python -c "from app.db import init_db; init_db()" || exit 1

python -m app.health &
python -m app.scheduler &
python -m app.bot &
wait -n
exit 1
