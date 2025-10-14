"""Check existing enum values in database"""
from app.db.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT e.enumlabel 
        FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = 'predictionsource'
        ORDER BY e.enumsortorder;
    """))
    
    print("Existing PredictionSource enum values:")
    for row in result:
        print(f"  '{row[0]}'")

