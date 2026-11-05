Schema migrations are managed by Alembic in `backend/migrations/` so they ship with the backend
image and run as the Helm pre-install/pre-upgrade hook. This directory intentionally holds no
SQL migrations.
