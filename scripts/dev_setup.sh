#!/bin/bash
set -e

echo "=== DataSphere Dev Setup ==="

# Check Python version
python3 --version | grep -E "3\.(11|12)" || { echo "Python 3.11+ required"; exit 1; }

# Install in dev mode
pip install -e ".[api,test]"

# Create .env from example if not exists
[ -f .env ] || cp .env.example .env && echo "Created .env from .env.example"

# Create data dirs
mkdir -p ~/.datasphere/artifacts
mkdir -p ~/.datasphere

# Run quick smoke test
python -c "from datasphere.api.app import app; print('✓ API imports OK')"
python -c "from datasphere.generators import DbtProjectGenerator; print('✓ Generators import OK')"
python -c "from datasphere.client import DataSphereClient; print('✓ SDK imports OK')"

echo ""
echo "=== Setup Complete ==="
echo "Start API:  uvicorn datasphere.api.app:app --reload"
echo "Open UI:    http://localhost:8000/ui"
echo "Run tests:  python -m pytest tests/ -q"
echo "API docs:   http://localhost:8000/docs"
