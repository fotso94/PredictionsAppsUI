#!/bin/bash
# Test script

set -e

echo "🧪 Running tests..."

# Run pytest with coverage
pytest --cov=app --cov-report=html --cov-report=term-missing

echo "✅ Tests completed!"
echo "📊 Coverage report generated in htmlcov/index.html"

