#!/bin/bash
# Smoke test: build, start, test health, test check, tear down
set -e

echo "=== Building containers ==="
docker compose build

echo "=== Starting containers ==="
docker compose up -d

echo "=== Waiting for backend ==="
for i in $(seq 1 30); do
    if curl -sf http://localhost:8080/api/health > /dev/null 2>&1; then
        echo "Backend is up"
        break
    fi
    sleep 1
done

echo "=== Testing health endpoint ==="
HEALTH=$(curl -sf -u admin:changeme http://localhost:8080/api/health)
echo "Health: $HEALTH"

echo "=== Testing check endpoint with invalid token ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -u admin:changeme \
  -X POST http://localhost:8080/api/check \
  -H "Authorization: Bearer invalid" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test"}')
echo "Invalid token status: $STATUS (expected 401)"
[ "$STATUS" = "401" ] || { echo "FAIL"; exit 1; }

echo "=== Tearing down ==="
docker compose down

echo "=== ALL SMOKE TESTS PASSED ==="
