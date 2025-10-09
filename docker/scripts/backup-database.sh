#!/bin/bash

# PostgreSQL Database Backup Script
# This script creates a complete backup of the Soccer Predictions Platform database

set -e  # Exit on error

# Configuration
CONTAINER_NAME="soccer_predictions_postgres"
DB_NAME="soccer_predictions"
DB_USER="postgres"
BACKUP_DIR="./backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/soccer_predictions_${TIMESTAMP}.sql"
COMPRESSED_FILE="${BACKUP_FILE}.gz"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}PostgreSQL Database Backup${NC}"
echo -e "${GREEN}========================================${NC}"

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}Error: PostgreSQL container '${CONTAINER_NAME}' is not running${NC}"
    exit 1
fi

echo -e "${YELLOW}Creating backup...${NC}"
echo "Database: ${DB_NAME}"
echo "Backup file: ${BACKUP_FILE}"

# Create the backup using pg_dump
docker exec -t "${CONTAINER_NAME}" pg_dump -U "${DB_USER}" -d "${DB_NAME}" \
    --clean \
    --if-exists \
    --create \
    --encoding=UTF8 \
    --verbose \
    > "${BACKUP_FILE}" 2>&1

# Check if backup was successful
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Backup created successfully${NC}"
    
    # Compress the backup
    echo -e "${YELLOW}Compressing backup...${NC}"
    gzip "${BACKUP_FILE}"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Backup compressed successfully${NC}"
        
        # Get file size
        SIZE=$(du -h "${COMPRESSED_FILE}" | cut -f1)
        echo -e "${GREEN}Compressed backup size: ${SIZE}${NC}"
        echo -e "${GREEN}Backup location: ${COMPRESSED_FILE}${NC}"
        
        # List recent backups
        echo ""
        echo -e "${YELLOW}Recent backups:${NC}"
        ls -lh "${BACKUP_DIR}" | tail -n 5
        
        # Cleanup old backups (keep last 10)
        echo ""
        echo -e "${YELLOW}Cleaning up old backups (keeping last 10)...${NC}"
        ls -t "${BACKUP_DIR}"/*.sql.gz 2>/dev/null | tail -n +11 | xargs -r rm
        echo -e "${GREEN}✅ Cleanup complete${NC}"
    else
        echo -e "${RED}Error: Failed to compress backup${NC}"
        exit 1
    fi
else
    echo -e "${RED}Error: Backup failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Backup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "To restore this backup, run:"
echo "  ./scripts/restore-database.sh ${COMPRESSED_FILE}"

