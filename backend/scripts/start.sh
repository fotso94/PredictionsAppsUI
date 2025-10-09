#!/bin/bash
# Start script for development

set -e

echo "🚀 Starting Soccer Predictions Platform API..."

# Wait for PostgreSQL
echo "⏳ Waiting for PostgreSQL..."
while ! nc -z localhost 5432; do
  sleep 0.1
done
echo "✅ PostgreSQL is ready!"

# Wait for Redis
echo "⏳ Waiting for Redis..."
while ! nc -z localhost 6379; do
  sleep 0.1
done
echo "✅ Redis is ready!"

# Run migrations
echo "📦 Running database migrations..."
alembic upgrade head

# Start server
echo "🎯 Starting Uvicorn server..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

