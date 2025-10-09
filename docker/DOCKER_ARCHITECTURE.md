# Docker Architecture Documentation
## Soccer Predictions Platform - Local Development Environment

**Version**: 1.0  
**Created**: 2025-10-08  
**Jira Task**: KAN-30

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Service Architecture](#service-architecture)
3. [Network Architecture](#network-architecture)
4. [Volume Architecture](#volume-architecture)
5. [Security Architecture](#security-architecture)
6. [Scalability Considerations](#scalability-considerations)

---

## 🏗️ Architecture Overview

The Docker Compose setup implements a **microservices architecture** for local development, mirroring the production AWS deployment structure while remaining lightweight and developer-friendly.

### Design Principles

1. **Separation of Concerns**: Each service runs in its own container
2. **Data Persistence**: Volumes ensure data survives container restarts
3. **Network Isolation**: Private network for secure inter-service communication
4. **Health Monitoring**: Health checks ensure services are ready before dependencies start
5. **Configuration Management**: External configuration files for easy customization
6. **Development Optimization**: Hot reload, logging, and debugging capabilities

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Host Machine (macOS/Windows/Linux)              │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                    Docker Engine                                  │ │
│  │                                                                   │ │
│  │  ┌─────────────────────────────────────────────────────────────┐ │ │
│  │  │         Docker Network: soccer_predictions_network          │ │ │
│  │  │                  Subnet: 172.20.0.0/16                      │ │ │
│  │  │                                                             │ │ │
│  │  │  ┌──────────────────┐  ┌──────────────────┐               │ │ │
│  │  │  │   PostgreSQL     │  │      Redis       │               │ │ │
│  │  │  │   Container      │  │    Container     │               │ │ │
│  │  │  │                  │  │                  │               │ │ │
│  │  │  │  Image: postgres │  │  Image: redis    │               │ │ │
│  │  │  │  Version: 15     │  │  Version: 7      │               │ │ │
│  │  │  │  Port: 5432      │  │  Port: 6379      │               │ │ │
│  │  │  │                  │  │                  │               │ │ │
│  │  │  │  ┌────────────┐  │  │  ┌────────────┐  │               │ │ │
│  │  │  │  │  Volume    │  │  │  │  Volume    │  │               │ │ │
│  │  │  │  │ postgres_  │  │  │  │  redis_    │  │               │ │ │
│  │  │  │  │   data     │  │  │  │   data     │  │               │ │ │
│  │  │  │  └────────────┘  │  │  └────────────┘  │               │ │ │
│  │  │  └──────────────────┘  └──────────────────┘               │ │ │
│  │  │           │                      │                         │ │ │
│  │  │           └──────────┬───────────┘                         │ │ │
│  │  │                      │                                     │ │ │
│  │  │           ┌──────────▼───────────┐                         │ │ │
│  │  │           │      Adminer         │                         │ │ │
│  │  │           │     Container        │                         │ │ │
│  │  │           │                      │                         │ │ │
│  │  │           │  Image: adminer      │                         │ │ │
│  │  │           │  Port: 8080          │                         │ │ │
│  │  │           └──────────────────────┘                         │ │ │
│  │  │                      │                                     │ │ │
│  │  │           ┌──────────▼───────────┐                         │ │ │
│  │  │           │   Backend API        │                         │ │ │
│  │  │           │    Container         │                         │ │ │
│  │  │           │  (Coming Soon)       │                         │ │ │
│  │  │           │                      │                         │ │ │
│  │  │           │  Image: custom       │                         │ │ │
│  │  │           │  Port: 8000          │                         │ │ │
│  │  │           └──────────────────────┘                         │ │ │
│  │  └─────────────────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  Port Mappings:                                                        │
│  Host:5432  → Container:5432  (PostgreSQL)                            │
│  Host:6379  → Container:6379  (Redis)                                 │
│  Host:8080  → Container:8080  (Adminer)                               │
│  Host:8000  → Container:8000  (Backend API - Future)                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🐳 Service Architecture

### PostgreSQL Service

**Purpose**: Primary data store for all application data

**Architecture Details:**

```
PostgreSQL Container
├── Base Image: postgres:15-alpine
├── Container Name: soccer_predictions_postgres
├── Network: soccer_predictions_network
├── Port Mapping: 5432:5432
├── Volumes:
│   ├── postgres_data → /var/lib/postgresql/data (persistent)
│   ├── ./docker/postgres/init → /docker-entrypoint-initdb.d (read-only)
│   └── ./docker/postgres/conf → /etc/postgresql/conf.d (read-only)
├── Environment:
│   ├── POSTGRES_USER=postgres
│   ├── POSTGRES_PASSWORD=postgres123
│   └── POSTGRES_DB=soccer_predictions
├── Health Check:
│   ├── Command: pg_isready -U postgres -d soccer_predictions
│   ├── Interval: 10s
│   ├── Timeout: 5s
│   └── Retries: 5
└── Configuration:
    ├── max_connections: 200
    ├── shared_buffers: 256MB
    ├── effective_cache_size: 1GB
    └── work_mem: 4MB
```

**Initialization Process:**

1. Container starts with PostgreSQL 15
2. Runs initialization scripts from `/docker-entrypoint-initdb.d/`
3. Creates 5 schemas: users, predictions, ml_models, analytics, audit
4. Enables extensions: uuid-ossp, btree_gin, pg_trgm, pgcrypto
5. Creates custom enum types for all schemas
6. Sets up permissions and utility functions
7. Logs initialization status to `db_init_log` table

**Data Organization:**

```
soccer_predictions (database)
├── users (schema)
│   ├── users
│   ├── expert_profiles
│   ├── admin_profiles
│   └── ... (14 more tables)
├── predictions (schema)
│   ├── predictions
│   ├── matches
│   ├── prediction_results
│   └── ... (13 more tables)
├── ml_models (schema)
│   ├── ml_models
│   ├── ml_predictions
│   ├── ml_training_runs
│   └── ... (9 more tables)
├── analytics (schema)
│   ├── user_analytics
│   ├── prediction_analytics_summary
│   └── ... (11 more tables)
└── audit (schema)
    ├── audit_log
    ├── data_access_log
    └── ... (6 more tables)
```

### Redis Service

**Purpose**: Caching, session management, and real-time data

**Architecture Details:**

```
Redis Container
├── Base Image: redis:7-alpine
├── Container Name: soccer_predictions_redis
├── Network: soccer_predictions_network
├── Port Mapping: 6379:6379
├── Volumes:
│   ├── redis_data → /data (persistent)
│   └── ./docker/redis/redis.conf → /usr/local/etc/redis/redis.conf (read-only)
├── Health Check:
│   ├── Command: redis-cli ping
│   ├── Interval: 10s
│   ├── Timeout: 3s
│   └── Retries: 5
└── Configuration:
    ├── maxmemory: 512mb
    ├── maxmemory-policy: allkeys-lru
    ├── databases: 16
    └── persistence: RDB snapshots
```

**Database Allocation:**

```
Redis Databases (0-15)
├── DB 0: User sessions and authentication tokens
│   ├── session:{user_id}
│   ├── jwt:{token_hash}
│   └── refresh_token:{user_id}
├── DB 1: Prediction caching
│   ├── prediction:{prediction_id}
│   ├── match_predictions:{match_id}
│   └── user_predictions:{user_id}
├── DB 2: Expert tools cache
│   ├── expert_analytics:{expert_id}
│   ├── expert_performance:{expert_id}
│   └── expert_specialties:{expert_id}
├── DB 3: ML model predictions cache
│   ├── ml_prediction:{match_id}
│   ├── model_output:{model_id}:{match_id}
│   └── champion_model:metadata
├── DB 4: Real-time match data
│   ├── live_match:{match_id}
│   ├── match_events:{match_id}
│   └── match_statistics:{match_id}
├── DB 5: API rate limiting
│   ├── rate_limit:{user_id}:{endpoint}
│   ├── api_quota:{user_id}
│   └── request_count:{user_id}:{hour}
└── DB 6-15: Reserved for future use
```

### Adminer Service

**Purpose**: Web-based database management interface

**Architecture Details:**

```
Adminer Container
├── Base Image: adminer:latest
├── Container Name: soccer_predictions_adminer
├── Network: soccer_predictions_network
├── Port Mapping: 8080:8080
├── Environment:
│   ├── ADMINER_DEFAULT_SERVER=postgres
│   └── ADMINER_DESIGN=pepa-linha
└── Dependencies:
    └── postgres (waits for healthy status)
```

**Features:**
- SQL query execution
- Table browsing and editing
- Database schema visualization
- Import/Export capabilities
- Multi-schema support

---

## 🌐 Network Architecture

### Docker Network Configuration

**Network Name**: `soccer_predictions_network`  
**Driver**: bridge  
**Subnet**: 172.20.0.0/16

**Network Topology:**

```
172.20.0.0/16 (soccer_predictions_network)
│
├── 172.20.0.2 → postgres (dynamic IP)
├── 172.20.0.3 → redis (dynamic IP)
├── 172.20.0.4 → adminer (dynamic IP)
└── 172.20.0.5 → backend (future, dynamic IP)
```

**Service Discovery:**

Services communicate using container names as hostnames:
- `postgres` → PostgreSQL service
- `redis` → Redis service
- `adminer` → Adminer service

**Example Connection Strings:**

```bash
# PostgreSQL (from backend container)
DATABASE_URL=postgresql://postgres:postgres123@postgres:5432/soccer_predictions

# Redis (from backend container)
REDIS_URL=redis://redis:6379/0

# PostgreSQL (from host machine)
DATABASE_URL=postgresql://postgres:postgres123@localhost:5432/soccer_predictions

# Redis (from host machine)
REDIS_URL=redis://localhost:6379/0
```

### Port Mappings

| Service | Container Port | Host Port | Protocol | Purpose |
|---------|---------------|-----------|----------|---------|
| PostgreSQL | 5432 | 5432 | TCP | Database connections |
| Redis | 6379 | 6379 | TCP | Cache connections |
| Adminer | 8080 | 8080 | HTTP | Web UI access |
| Backend | 8000 | 8000 | HTTP | API endpoints (future) |

---

## 💾 Volume Architecture

### Volume Strategy

**Persistent Volumes**: Data survives container restarts and removals

```
Docker Volumes
├── postgres_data
│   ├── Name: soccer_predictions_postgres_data
│   ├── Driver: local
│   ├── Mount Point: /var/lib/postgresql/data
│   ├── Purpose: PostgreSQL database files
│   └── Size: ~10GB (estimated Year 1)
│
└── redis_data
    ├── Name: soccer_predictions_redis_data
    ├── Driver: local
    ├── Mount Point: /data
    ├── Purpose: Redis RDB snapshots
    └── Size: ~512MB (max memory limit)
```

**Bind Mounts**: Configuration files (read-only)

```
Bind Mounts
├── ./docker/postgres/init → /docker-entrypoint-initdb.d
│   ├── Purpose: Database initialization scripts
│   ├── Mode: Read-only
│   └── Files: 01-init-database.sql
│
├── ./docker/postgres/conf → /etc/postgresql/conf.d
│   ├── Purpose: PostgreSQL configuration
│   ├── Mode: Read-only
│   └── Files: postgresql.conf
│
└── ./docker/redis/redis.conf → /usr/local/etc/redis/redis.conf
    ├── Purpose: Redis configuration
    ├── Mode: Read-only
    └── Files: redis.conf
```

### Volume Management

**Backup Strategy:**

```bash
# PostgreSQL backup
docker-compose exec postgres pg_dump -U postgres -d soccer_predictions > backup.sql

# Redis backup
docker-compose exec redis redis-cli BGSAVE
docker cp soccer_predictions_redis:/data/dump.rdb ./redis_backup.rdb
```

**Restore Strategy:**

```bash
# PostgreSQL restore
docker-compose exec -T postgres psql -U postgres -d soccer_predictions < backup.sql

# Redis restore
docker cp ./redis_backup.rdb soccer_predictions_redis:/data/dump.rdb
docker-compose restart redis
```

---

## 🔒 Security Architecture

### Security Layers

**1. Network Isolation**

- All services run in isolated Docker network
- No direct external access except through mapped ports
- Inter-service communication uses internal network

**2. Access Control**

- PostgreSQL: Username/password authentication
- Redis: No password for local development (can be enabled)
- Adminer: Requires PostgreSQL credentials

**3. Data Protection**

- Persistent volumes for data durability
- Read-only configuration files prevent tampering
- Health checks ensure service availability

**4. Development vs Production**

| Feature | Development | Production |
|---------|-------------|------------|
| PostgreSQL Password | Simple (postgres123) | Strong, rotated |
| Redis Password | None | Required |
| SSL/TLS | Disabled | Required |
| Network | Bridge | VPC with security groups |
| Volumes | Local | EBS with encryption |
| Backups | Manual | Automated with retention |

---

## 📈 Scalability Considerations

### Local Development Limits

**Current Configuration:**
- PostgreSQL: 200 max connections
- Redis: 512MB max memory
- Single instance per service

**Scaling for Production:**

```
Local Development → AWS Production
│
├── PostgreSQL
│   ├── Single container → RDS Multi-AZ
│   ├── 200 connections → 1000+ connections
│   ├── Local volume → EBS with auto-scaling
│   └── Manual backups → Automated backups with PITR
│
├── Redis
│   ├── Single container → ElastiCache cluster
│   ├── 512MB memory → Multi-GB with replication
│   ├── RDB snapshots → AOF + RDB with replication
│   └── Single DB → Multiple cache nodes
│
└── Backend
    ├── Single container → ECS Fargate with auto-scaling
    ├── Hot reload → Blue/green deployments
    └── Local network → ALB with health checks
```

### Resource Allocation

**Recommended Docker Desktop Settings:**

- **CPUs**: 4+ cores
- **Memory**: 8GB+ RAM
- **Disk**: 20GB+ free space
- **Swap**: 2GB+

**Service Resource Usage:**

| Service | CPU | Memory | Disk |
|---------|-----|--------|------|
| PostgreSQL | 1-2 cores | 512MB-1GB | 10GB+ |
| Redis | 0.5-1 core | 512MB | 512MB |
| Adminer | 0.1 core | 128MB | 50MB |
| Backend | 1-2 cores | 512MB-1GB | 1GB |

---

## 🔗 Related Documentation

- [Docker README](./README.md) - Quick start and usage guide
- [Database Schema Documentation](../docs/database/README.md)
- [Local Development Architecture Plan](../LOCAL_DEVELOPMENT_ARCHITECTURE_PLAN.md)
- [AWS Production Deployment Plan](../AWS_PRODUCTION_DEPLOYMENT_PLAN.md)

---

**Status**: ✅ Complete  
**Last Updated**: 2025-10-08  
**Maintained By**: Backend Development Team


