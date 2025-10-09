# Redis Configuration
## Soccer Predictions Platform - Cache and Session Management

**Version**: 1.0  
**Created**: 2025-10-08  
**Jira Task**: KAN-104 - Configure Redis container for caching

---

## 📋 Overview

This directory contains Redis configuration for the Soccer Predictions Platform local development environment.

**Redis Version**: 7-alpine  
**Port**: 6379  
**Max Memory**: 512MB  
**Eviction Policy**: allkeys-lru  
**Persistence**: RDB snapshots

---

## 📁 Directory Structure

```
docker/redis/
├── README.md        # This file
└── redis.conf       # Redis server configuration
```

---

## ⚙️ Configuration

### Redis Configuration File: redis.conf

**Location**: `docker/redis/redis.conf`

**Key Settings:**

| Setting | Value | Purpose |
|---------|-------|---------|
| `port` | 6379 | Redis server port |
| `bind` | 0.0.0.0 | Listen on all interfaces |
| `protected-mode` | no | Allow Docker network access |
| `maxmemory` | 512mb | Maximum memory usage |
| `maxmemory-policy` | allkeys-lru | Evict least recently used keys |
| `databases` | 16 | Number of databases (0-15) |
| `save` | 900 1, 300 10, 60 10000 | RDB snapshot triggers |
| `appendonly` | no | AOF disabled (using RDB only) |
| `loglevel` | notice | Logging level |

### Database Allocation

Redis provides 16 databases (0-15). The Soccer Predictions Platform uses them as follows:

```
DB 0: User Sessions and Authentication
├── session:{user_id} → Session data (JSON)
├── jwt:{token_hash} → JWT token metadata
├── refresh_token:{user_id} → Refresh token
└── user_online:{user_id} → Online status

DB 1: Prediction Caching
├── prediction:{prediction_id} → Prediction details
├── match_predictions:{match_id} → All predictions for match
├── user_predictions:{user_id} → User's predictions
└── published_predictions → List of published predictions

DB 2: Expert Tools Cache
├── expert_analytics:{expert_id} → Expert performance data
├── expert_performance:{expert_id} → Performance metrics
├── expert_specialties:{expert_id} → Specialty areas
└── expert_leaderboard → Expert rankings

DB 3: ML Model Predictions Cache
├── ml_prediction:{match_id} → ML baseline prediction
├── model_output:{model_id}:{match_id} → Specific model output
├── champion_model:metadata → Current champion model info
└── model_performance → Model performance metrics

DB 4: Real-time Match Data
├── live_match:{match_id} → Live match data
├── match_events:{match_id} → Match events (goals, cards, etc.)
├── match_statistics:{match_id} → Live statistics
└── live_matches → List of currently live matches

DB 5: API Rate Limiting
├── rate_limit:{user_id}:{endpoint} → Request count
├── api_quota:{user_id} → API quota usage
├── request_count:{user_id}:{hour} → Hourly request count
└── blocked_ips → Blocked IP addresses

DB 6-15: Reserved for Future Use
└── Available for new features
```

### Memory Management

**Max Memory**: 512MB for local development

**Eviction Policy**: `allkeys-lru` (Least Recently Used)
- When max memory is reached, Redis evicts the least recently used keys
- Applies to all keys, not just those with TTL
- Suitable for caching use case

**Alternative Policies:**
- `volatile-lru`: Evict LRU keys with TTL only
- `allkeys-random`: Evict random keys
- `volatile-ttl`: Evict keys with shortest TTL
- `noeviction`: Return errors when memory limit reached

### Persistence Strategy

**RDB Snapshots** (enabled):
- Save after 900 seconds (15 min) if at least 1 key changed
- Save after 300 seconds (5 min) if at least 10 keys changed
- Save after 60 seconds if at least 10,000 keys changed

**AOF** (disabled for local development):
- Append-only file disabled to reduce disk I/O
- RDB snapshots sufficient for development
- Enable AOF in production for better durability

---

## 🚀 Common Operations

### Connect to Redis

```bash
# Using redis-cli in container
docker-compose exec redis redis-cli

# Connect to specific database
docker-compose exec redis redis-cli -n 1

# From host (requires redis-cli installed)
redis-cli -h localhost -p 6379
```

### Basic Commands

```bash
# Ping server
docker-compose exec redis redis-cli ping
# Returns: PONG

# Select database
docker-compose exec redis redis-cli SELECT 0

# Set key with value
docker-compose exec redis redis-cli SET mykey "myvalue"

# Set key with expiration (seconds)
docker-compose exec redis redis-cli SETEX mykey 3600 "myvalue"

# Get value
docker-compose exec redis redis-cli GET mykey

# Delete key
docker-compose exec redis redis-cli DEL mykey

# Check if key exists
docker-compose exec redis redis-cli EXISTS mykey

# Get TTL (time to live)
docker-compose exec redis redis-cli TTL mykey

# List all keys (use with caution in production)
docker-compose exec redis redis-cli KEYS "*"

# Get key count
docker-compose exec redis redis-cli DBSIZE
```

### Session Management (DB 0)

```bash
# Select session database
docker-compose exec redis redis-cli SELECT 0

# Store session
docker-compose exec redis redis-cli SETEX "session:user123" 3600 '{"user_id":"123","email":"user@example.com"}'

# Get session
docker-compose exec redis redis-cli GET "session:user123"

# Delete session (logout)
docker-compose exec redis redis-cli DEL "session:user123"

# List all sessions
docker-compose exec redis redis-cli KEYS "session:*"
```

### Prediction Caching (DB 1)

```bash
# Select prediction database
docker-compose exec redis redis-cli SELECT 1

# Cache prediction
docker-compose exec redis redis-cli SETEX "prediction:match456" 1800 '{"match_id":"456","prediction":"home_win","confidence":0.85}'

# Get cached prediction
docker-compose exec redis redis-cli GET "prediction:match456"

# Cache match predictions list
docker-compose exec redis redis-cli SETEX "match_predictions:match456" 1800 '["pred1","pred2","pred3"]'
```

### Rate Limiting (DB 5)

```bash
# Select rate limit database
docker-compose exec redis redis-cli SELECT 5

# Increment request count
docker-compose exec redis redis-cli INCR "rate_limit:user123:/api/predictions"

# Set expiration (1 hour)
docker-compose exec redis redis-cli EXPIRE "rate_limit:user123:/api/predictions" 3600

# Get request count
docker-compose exec redis redis-cli GET "rate_limit:user123:/api/predictions"

# Check if user exceeded limit
# If count > limit, return error
```

---

## 📊 Monitoring

### Memory Usage

```bash
# Get memory info
docker-compose exec redis redis-cli INFO memory

# Key metrics:
# - used_memory_human: Current memory usage
# - used_memory_peak_human: Peak memory usage
# - maxmemory_human: Max memory limit
# - mem_fragmentation_ratio: Fragmentation ratio
```

### Statistics

```bash
# Get stats
docker-compose exec redis redis-cli INFO stats

# Key metrics:
# - total_connections_received: Total connections
# - total_commands_processed: Total commands
# - instantaneous_ops_per_sec: Current ops/sec
# - keyspace_hits: Cache hits
# - keyspace_misses: Cache misses
# - evicted_keys: Keys evicted due to maxmemory
```

### Keyspace Information

```bash
# Get keyspace info (all databases)
docker-compose exec redis redis-cli INFO keyspace

# Example output:
# db0:keys=150,expires=100,avg_ttl=3600000
# db1:keys=500,expires=450,avg_ttl=1800000
```

### Real-time Monitoring

```bash
# Monitor all commands in real-time
docker-compose exec redis redis-cli MONITOR

# Check slow log
docker-compose exec redis redis-cli SLOWLOG GET 10

# Reset slow log
docker-compose exec redis redis-cli SLOWLOG RESET
```

---

## 🔧 Maintenance

### Backup

```bash
# Trigger background save
docker-compose exec redis redis-cli BGSAVE

# Check last save time
docker-compose exec redis redis-cli LASTSAVE

# Copy RDB file
docker cp soccer_predictions_redis:/data/dump.rdb ./redis_backup.rdb
```

### Restore

```bash
# Stop Redis
docker-compose stop redis

# Copy backup to volume
docker cp ./redis_backup.rdb soccer_predictions_redis:/data/dump.rdb

# Start Redis
docker-compose start redis
```

### Flush Data

```bash
# Flush current database
docker-compose exec redis redis-cli FLUSHDB

# Flush all databases (CAUTION!)
docker-compose exec redis redis-cli FLUSHALL
```

### Configuration Changes

```bash
# Get current configuration
docker-compose exec redis redis-cli CONFIG GET maxmemory

# Set configuration at runtime (temporary)
docker-compose exec redis redis-cli CONFIG SET maxmemory 1gb

# Make permanent changes
# Edit docker/redis/redis.conf
# Restart Redis
docker-compose restart redis
```

---

## 🔍 Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs redis

# Common issues:
# 1. Port 6379 already in use
lsof -i :6379

# 2. Configuration syntax error
docker-compose exec redis cat /usr/local/etc/redis/redis.conf

# 3. Permission issues
docker-compose exec redis ls -la /data
```

### Cannot Connect

```bash
# Check service is running
docker-compose ps redis

# Test connection
docker-compose exec redis redis-cli ping

# Check from host
redis-cli -h localhost -p 6379 ping
```

### Memory Issues

```bash
# Check memory usage
docker-compose exec redis redis-cli INFO memory | grep used_memory_human

# Check evicted keys
docker-compose exec redis redis-cli INFO stats | grep evicted_keys

# Increase max memory
# Edit docker/redis/redis.conf
maxmemory 1gb

# Restart Redis
docker-compose restart redis
```

### Performance Issues

```bash
# Check slow log
docker-compose exec redis redis-cli SLOWLOG GET 10

# Check operations per second
docker-compose exec redis redis-cli INFO stats | grep instantaneous_ops_per_sec

# Check connected clients
docker-compose exec redis redis-cli INFO clients
```

---

## 🎯 Best Practices

### Key Naming Conventions

Use consistent, hierarchical key names:

```
{domain}:{entity}:{id}
{domain}:{entity}:{id}:{attribute}

Examples:
session:user123
prediction:match456
ml_prediction:match456
rate_limit:user123:/api/predictions
```

### TTL (Time To Live)

Always set TTL on cached data:

```bash
# Session: 1 hour
SETEX session:user123 3600 "data"

# Prediction cache: 30 minutes
SETEX prediction:match456 1800 "data"

# Live match data: 5 minutes
SETEX live_match:match456 300 "data"

# Rate limit: 1 hour
SETEX rate_limit:user123 3600 "count"
```

### Data Types

Use appropriate Redis data types:

- **Strings**: Simple key-value (sessions, cache)
- **Hashes**: Objects with multiple fields (user profiles)
- **Lists**: Ordered collections (recent predictions)
- **Sets**: Unique collections (online users)
- **Sorted Sets**: Ranked collections (leaderboards)

### Memory Optimization

```bash
# Use hashes for objects instead of JSON strings
HSET user:123 name "John" email "john@example.com"

# Use shorter key names
# Instead of: user_session_data:user_id_123
# Use: session:123

# Set appropriate TTL to auto-expire old data
SETEX key 3600 "value"
```

---

## 📚 Related Documentation

- [Docker README](../README.md) - Main Docker documentation
- [Docker Architecture](../DOCKER_ARCHITECTURE.md) - Architecture details
- [Troubleshooting Guide](../TROUBLESHOOTING.md) - Problem solving
- [Redis Official Documentation](https://redis.io/documentation)

---

**Status**: ✅ Complete  
**Last Updated**: 2025-10-08  
**Maintained By**: Backend Development Team


