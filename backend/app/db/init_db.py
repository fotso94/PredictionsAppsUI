"""
Database Initialization
Create schemas and initial data
"""

import logging
from sqlalchemy import text
from app.db.session import engine

logger = logging.getLogger(__name__)


def init_db() -> None:
    """
    Initialize database
    - Verify connection
    - Check if schemas exist (created by Docker init script)
    """
    try:
        # Test database connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            logger.info(f"Connected to PostgreSQL: {version}")
            
            # Check if schemas exist
            result = conn.execute(
                text("""
                    SELECT schema_name 
                    FROM information_schema.schemata 
                    WHERE schema_name IN ('users', 'predictions', 'ml_models', 'analytics', 'audit')
                    ORDER BY schema_name
                """)
            )
            schemas = [row[0] for row in result]
            
            if len(schemas) == 5:
                logger.info(f"All 5 schemas found: {', '.join(schemas)}")
            else:
                logger.warning(f"Only {len(schemas)} schemas found: {', '.join(schemas)}")
                logger.warning("Expected schemas: users, predictions, ml_models, analytics, audit")
                logger.warning("Run Docker initialization script to create missing schemas")
            
            conn.commit()
            
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

