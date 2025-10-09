#!/usr/bin/env python3
"""
Test Database and Redis Connections
Comprehensive testing script for PostgreSQL and Redis connectivity
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import redis
from redis.exceptions import RedisError
from app.core.config import settings
from app.core.redis import (
    get_redis_client,
    get_sessions_redis,
    get_predictions_redis,
    get_expert_tools_redis,
    get_ml_models_redis,
    get_match_data_redis,
    get_rate_limit_redis,
)


def print_header(title: str):
    """Print a formatted header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_success(message: str):
    """Print success message"""
    print(f"✅ {message}")


def print_error(message: str):
    """Print error message"""
    print(f"❌ {message}")


def print_info(message: str):
    """Print info message"""
    print(f"ℹ️  {message}")


def test_postgresql_connection():
    """Test PostgreSQL database connection"""
    print_header("Testing PostgreSQL Connection")
    
    try:
        # Create engine
        engine = create_engine(settings.DATABASE_URL, echo=False)
        
        # Test connection
        with engine.connect() as conn:
            # Get PostgreSQL version
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            print_success(f"Connected to PostgreSQL")
            print_info(f"Version: {version}")
            
            # Test basic query
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
            print_success("Basic query test passed")
            
            # Check current database
            result = conn.execute(text("SELECT current_database()"))
            db_name = result.scalar()
            print_info(f"Current database: {db_name}")
            
            # Check schemas
            result = conn.execute(text("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name IN ('users', 'predictions', 'ml_models', 'analytics', 'audit')
                ORDER BY schema_name
            """))
            schemas = [row[0] for row in result]
            print_success(f"Found {len(schemas)} schemas: {', '.join(schemas)}")
            
            # Check tables in each schema
            for schema in schemas:
                result = conn.execute(text(f"""
                    SELECT COUNT(*) 
                    FROM information_schema.tables 
                    WHERE table_schema = '{schema}'
                """))
                table_count = result.scalar()
                print_info(f"  {schema}: {table_count} tables")
        
        engine.dispose()
        return True
        
    except SQLAlchemyError as e:
        print_error(f"PostgreSQL connection failed: {str(e)}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        return False


def test_redis_connection():
    """Test Redis connection"""
    print_header("Testing Redis Connection")
    
    try:
        # Test main Redis client
        client = get_redis_client()
        
        # Ping test
        response = client.ping()
        assert response is True
        print_success("Redis PING successful")
        
        # Get Redis info
        info = client.info()
        print_info(f"Redis version: {info['redis_version']}")
        print_info(f"Connected clients: {info['connected_clients']}")
        print_info(f"Used memory: {info['used_memory_human']}")
        
        # Test SET/GET
        test_key = "test:connection"
        test_value = "Hello from FastAPI!"
        client.set(test_key, test_value, ex=10)  # Expire in 10 seconds
        retrieved = client.get(test_key)
        assert retrieved == test_value
        print_success("SET/GET test passed")
        
        # Clean up
        client.delete(test_key)
        print_success("Cleanup successful")
        
        return True
        
    except RedisError as e:
        print_error(f"Redis connection failed: {str(e)}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        return False


def test_redis_databases():
    """Test all Redis database allocations"""
    print_header("Testing Redis Database Allocations")
    
    databases = {
        "Sessions (DB 0)": get_sessions_redis,
        "Predictions (DB 1)": get_predictions_redis,
        "Expert Tools (DB 2)": get_expert_tools_redis,
        "ML Models (DB 3)": get_ml_models_redis,
        "Match Data (DB 4)": get_match_data_redis,
        "Rate Limiting (DB 5)": get_rate_limit_redis,
    }
    
    all_passed = True
    
    for name, get_client_func in databases.items():
        try:
            client = get_client_func()
            
            # Ping test
            response = client.ping()
            assert response is True
            
            # Test SET/GET
            test_key = f"test:{name.lower().replace(' ', '_')}"
            client.set(test_key, "test_value", ex=5)
            value = client.get(test_key)
            assert value == "test_value"
            client.delete(test_key)
            
            print_success(f"{name}: Connected and tested")
            
        except Exception as e:
            print_error(f"{name}: Failed - {str(e)}")
            all_passed = False
    
    return all_passed


def test_connection_pooling():
    """Test connection pooling"""
    print_header("Testing Connection Pooling")
    
    try:
        # PostgreSQL connection pool
        engine = create_engine(settings.DATABASE_URL, echo=False)
        
        # Create multiple connections
        connections = []
        for i in range(5):
            conn = engine.connect()
            connections.append(conn)
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
        
        print_success(f"Created {len(connections)} PostgreSQL connections")
        
        # Close all connections
        for conn in connections:
            conn.close()
        
        engine.dispose()
        print_success("All PostgreSQL connections closed")
        
        # Redis connection pool
        client = get_redis_client()
        pool = client.connection_pool
        print_info(f"Redis connection pool created")
        print_info(f"Max connections: {pool.max_connections}")
        
        # Test multiple operations
        for i in range(10):
            client.set(f"test:pool:{i}", f"value_{i}", ex=5)
            value = client.get(f"test:pool:{i}")
            assert value == f"value_{i}"
            client.delete(f"test:pool:{i}")
        
        print_success("Redis connection pool test passed")
        
        return True
        
    except Exception as e:
        print_error(f"Connection pooling test failed: {str(e)}")
        return False


def test_error_handling():
    """Test error handling for connection failures"""
    print_header("Testing Error Handling")
    
    # Test invalid PostgreSQL connection
    try:
        invalid_url = "postgresql://invalid:invalid@localhost:9999/invalid"
        engine = create_engine(invalid_url, echo=False)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print_error("Should have failed with invalid PostgreSQL connection")
        return False
    except Exception:
        print_success("PostgreSQL error handling works correctly")
    
    # Test invalid Redis connection
    try:
        invalid_client = redis.Redis(host='invalid-host', port=9999, socket_timeout=1)
        invalid_client.ping()
        print_error("Should have failed with invalid Redis connection")
        return False
    except Exception:
        print_success("Redis error handling works correctly")
    
    return True


def main():
    """Run all connection tests"""
    print("\n" + "🧪" * 35)
    print("  DATABASE AND REDIS CONNECTION TESTS")
    print("🧪" * 35)
    
    print_info(f"Environment: {settings.ENVIRONMENT}")
    print_info(f"Database URL: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'N/A'}")
    print_info(f"Redis URL: {settings.REDIS_URL}")
    
    results = {
        "PostgreSQL Connection": test_postgresql_connection(),
        "Redis Connection": test_redis_connection(),
        "Redis Databases": test_redis_databases(),
        "Connection Pooling": test_connection_pooling(),
        "Error Handling": test_error_handling(),
    }
    
    # Print summary
    print_header("Test Summary")
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print("\n" + "-" * 70)
    print(f"Total: {passed}/{total} tests passed")
    print("-" * 70 + "\n")
    
    # Exit with appropriate code
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

