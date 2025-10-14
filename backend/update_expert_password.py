"""
Script to update expert user password
Usage: python update_expert_password.py
"""

import sys
from sqlalchemy.orm import Session
from sqlalchemy import select

# Add parent directory to path
sys.path.insert(0, '.')

from app.db.session import SessionLocal
from app.models.users import User
from app.core.security import get_password_hash


def update_password(email: str, new_password: str):
    """Update user password"""
    db = SessionLocal()
    
    try:
        # Get user
        user = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        
        if not user:
            print(f"❌ User with email {email} not found!")
            return
        
        # Update password
        user.password_hash = get_password_hash(new_password)
        db.commit()
        
        print(f"✅ Password updated successfully for {email}")
        print(f"   New password: {new_password}")
        
    except Exception as e:
        print(f"❌ Error updating password: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    update_password("blake2lang@gmail.com", "Jesuis237")

