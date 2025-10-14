"""Check existing enum types in database"""
from app.db.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT n.nspname as schema, t.typname as typename 
        FROM pg_type t 
        LEFT JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace 
        WHERE t.typtype = 'e'
        AND n.nspname IN ('predictions', 'users', 'ml_models', 'analytics', 'audit')
        ORDER BY 1, 2;
    """))
    
    print("Existing enum types:")
    for row in result:
        print(f"  {row[0]}.{row[1]}")

