#!/bin/bash

# PostgreSQL Database Restore Script
# This script restores a database backup to the Soccer Predictions Platform database

set -e  # Exit on error

# Configuration
CONTAINER_NAME="soccer_predictions_postgres"
DB_NAME="soccer_predictions"
DB_USER="postgres"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}PostgreSQL Database Restore${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if backup file is provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: No backup file specified${NC}"
    echo "Usage: $0 <backup_file.sql.gz>"
    echo ""
    echo "Available backups:"
    ls -lh ./backups/*.sql.gz 2>/dev/null || echo "No backups found"
    exit 1
fi

BACKUP_FILE="$1"

# Check if backup file exists
if [ ! -f "${BACKUP_FILE}" ]; then
    echo -e "${RED}Error: Backup file '${BACKUP_FILE}' not found${NC}"
    exit 1
fi

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}Error: PostgreSQL container '${CONTAINER_NAME}' is not running${NC}"
    exit 1
fi

echo -e "${YELLOW}Backup file: ${BACKUP_FILE}${NC}"
echo -e "${YELLOW}Database: ${DB_NAME}${NC}"
echo ""

# Warning
echo -e "${RED}⚠️  WARNING: This will DROP and RECREATE the database!${NC}"
echo -e "${RED}⚠️  All existing data will be LOST!${NC}"
echo ""
read -p "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo -e "${YELLOW}Restore cancelled${NC}"
    exit 0
fi

echo ""
echo -e "${YELLOW}Decompressing backup...${NC}"

# Decompress and restore
if [[ "${BACKUP_FILE}" == *.gz ]]; then
    gunzip -c "${BACKUP_FILE}" | docker exec -i "${CONTAINER_NAME}" psql -U "${DB_USER}" -d postgres
else
    cat "${BACKUP_FILE}" | docker exec -i "${CONTAINER_NAME}" psql -U "${DB_USER}" -d postgres
fi

# Check if restore was successful
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Database restored successfully${NC}"
    
    # Verify the restore
    echo ""
    echo -e "${YELLOW}Verifying restore...${NC}"
    
    # Check schemas
    SCHEMAS=$(docker exec -t "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}" -t -c \
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('users', 'predictions', 'ml_models', 'analytics', 'audit') ORDER BY schema_name;")
    
    echo "Schemas found:"
    echo "${SCHEMAS}"
    
    # Count tables
    TABLE_COUNT=$(docker exec -t "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}" -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('users', 'predictions', 'ml_models', 'analytics', 'audit');")
    
    echo "Total tables: ${TABLE_COUNT}"
    
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Restore Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${RED}Error: Restore failed${NC}"
    exit 1
fi

