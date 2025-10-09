#!/bin/bash
# Quick API Connection Testing Script
# Tests all health endpoints and displays results

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# API base URL
API_URL="${API_URL:-http://localhost:8000}"

echo ""
echo "=========================================="
echo "  API Connection Tests"
echo "=========================================="
echo ""
echo "API URL: $API_URL"
echo ""

# Function to test endpoint
test_endpoint() {
    local endpoint=$1
    local description=$2
    
    echo -e "${BLUE}Testing:${NC} $description"
    echo -e "${YELLOW}Endpoint:${NC} $endpoint"
    
    response=$(curl -s -w "\n%{http_code}" "$API_URL$endpoint")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 200 ]; then
        echo -e "${GREEN}✅ Status: $http_code OK${NC}"
        echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
    else
        echo -e "${RED}❌ Status: $http_code FAILED${NC}"
        echo "$body"
    fi
    
    echo ""
}

# Test 1: Root endpoint
test_endpoint "/" "Root Endpoint"

# Test 2: Basic health check
test_endpoint "/health" "Basic Health Check"

# Test 3: API v1 health check
test_endpoint "/api/v1/health" "API v1 Health Check"

# Test 4: Detailed health check (Database + Redis)
test_endpoint "/api/v1/health/detailed" "Detailed Health Check (DB + Redis)"

# Test 5: Database health check
test_endpoint "/api/v1/health/database" "Database Health Check"

# Test 6: Redis health check
test_endpoint "/api/v1/health/redis" "Redis Health Check"

echo "=========================================="
echo "  Direct Database Tests"
echo "=========================================="
echo ""

# Test PostgreSQL connection directly
echo -e "${BLUE}Testing:${NC} Direct PostgreSQL Connection"
if docker exec soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "SELECT version();" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ PostgreSQL: Connected${NC}"
    docker exec soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "SELECT version();" | head -n 3
    echo ""
    
    # Check schemas
    echo -e "${BLUE}Checking:${NC} Database Schemas"
    docker exec soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('users', 'predictions', 'ml_models', 'analytics', 'audit') ORDER BY schema_name;"
    echo ""
else
    echo -e "${RED}❌ PostgreSQL: Connection failed${NC}"
    echo ""
fi

# Test Redis connection directly
echo -e "${BLUE}Testing:${NC} Direct Redis Connection"
if docker exec soccer_predictions_redis redis-cli PING > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Redis: Connected${NC}"
    echo "PONG: $(docker exec soccer_predictions_redis redis-cli PING)"
    echo ""
    
    # Get Redis info
    echo -e "${BLUE}Redis Info:${NC}"
    docker exec soccer_predictions_redis redis-cli INFO server | grep -E "redis_version|os|arch_bits"
    echo ""
    
    # Test all databases
    echo -e "${BLUE}Testing:${NC} Redis Databases (0-5)"
    for db in {0..5}; do
        result=$(docker exec soccer_predictions_redis redis-cli -n $db PING)
        if [ "$result" = "PONG" ]; then
            echo -e "${GREEN}✅ DB $db: Connected${NC}"
        else
            echo -e "${RED}❌ DB $db: Failed${NC}"
        fi
    done
    echo ""
else
    echo -e "${RED}❌ Redis: Connection failed${NC}"
    echo ""
fi

echo "=========================================="
echo "  Summary"
echo "=========================================="
echo ""
echo -e "${GREEN}All tests completed!${NC}"
echo ""
echo "To run Python connection tests:"
echo "  cd backend"
echo "  source venv/bin/activate"
echo "  python scripts/test_connections.py"
echo ""

