"""
Script to create an expert user in the database
Usage: python create_expert_user.py
"""

import sys
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import select

# Add parent directory to path
sys.path.insert(0, '.')

from app.db.session import SessionLocal
from app.models.users import User, UserType, AccountStatus, ExpertProfile
from app.core.security import get_password_hash


def create_expert_user(
    db: Session,
    email: str,
    password: str,
    first_name: str = "Blake",
    last_name: str = "Lang",
    is_verified: bool = True
) -> User:
    """
    Create an expert user with verified status

    Args:
        db: Database session
        email: User email
        password: User password (will be hashed)
        first_name: User's first name
        last_name: User's last name
        is_verified: Whether the expert is verified

    Returns:
        Created User object
    """
    
    # Check if user already exists
    existing_user = db.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()
    
    if existing_user:
        print(f"❌ User with email {email} already exists!")
        print(f"   User ID: {existing_user.id}")
        print(f"   User Type: {existing_user.user_type}")
        print(f"   Account Status: {existing_user.account_status}")
        
        # Check if expert profile exists
        if existing_user.user_type == UserType.EXPERT:
            expert_profile = db.execute(
                select(ExpertProfile).where(ExpertProfile.user_id == existing_user.id)
            ).scalar_one_or_none()
            
            if expert_profile:
                print(f"   Expert Verified: {expert_profile.is_verified}")
                
                # Update verification status if needed
                if not expert_profile.is_verified and is_verified:
                    expert_profile.is_verified = True
                    db.commit()
                    print(f"✅ Updated expert verification status to: {is_verified}")
            else:
                # Create expert profile if missing
                print("   Creating missing expert profile...")
                expert_profile = ExpertProfile(
                    user_id=existing_user.id,
                    is_verified=is_verified,
                    bio="Expert soccer analyst and predictor with deep knowledge of football analytics",
                    expertise_areas={"leagues": ["Premier League", "La Liga", "Serie A"], "specialties": ["Match Predictions", "Statistical Analysis"]},
                    years_of_experience=5,
                    total_predictions=0,
                    correct_predictions=0,
                    reputation_score=100,
                    follower_count=0,
                )
                db.add(expert_profile)
                db.commit()
                print(f"✅ Created expert profile with verification: {is_verified}")
        
        return existing_user
    
    # Create new user
    print(f"Creating new expert user: {email}")

    # Hash password
    password_hash = get_password_hash(password)

    # Generate username from email
    username = email.split('@')[0]

    # Create user
    user = User(
        email=email,
        username=username,
        password_hash=password_hash,
        first_name=first_name,
        last_name=last_name,
        user_type=UserType.EXPERT,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,  # Auto-verify email for expert users
    )
    
    db.add(user)
    db.flush()  # Flush to get user.id
    
    # Create expert profile
    expert_profile = ExpertProfile(
        user_id=user.id,
        is_verified=is_verified,
        bio="Expert soccer analyst and predictor with deep knowledge of football analytics",
        expertise_areas={"leagues": ["Premier League", "La Liga", "Serie A"], "specialties": ["Match Predictions", "Statistical Analysis"]},
        years_of_experience=5,
        total_predictions=0,
        correct_predictions=0,
        accuracy_score=None,  # Will be calculated based on predictions
        average_confidence=None,
        reputation_score=100,  # Starting reputation
        follower_count=0,
    )
    
    db.add(expert_profile)
    db.commit()
    db.refresh(user)
    
    print(f"✅ Successfully created expert user!")
    print(f"   User ID: {user.id}")
    print(f"   Email: {user.email}")
    print(f"   Username: {user.username}")
    print(f"   Name: {user.first_name} {user.last_name}")
    print(f"   User Type: {user.user_type}")
    print(f"   Account Status: {user.account_status}")
    print(f"   Email Verified: {user.email_verified}")
    print(f"   Expert Verified: {expert_profile.is_verified}")
    
    return user


def main():
    """Main function to create expert user"""

    print("=" * 60)
    print("Creating Expert User")
    print("=" * 60)

    # User credentials
    email = "blake2lang@gmail.com"
    password = "Jesuis237"  # Updated password
    first_name = "Blake"
    last_name = "Lang"
    is_verified = True

    print(f"\nUser Details:")
    print(f"  Email: {email}")
    print(f"  Password: {password}")
    print(f"  First Name: {first_name}")
    print(f"  Last Name: {last_name}")
    print(f"  Role: EXPERT")
    print(f"  Verified: {is_verified}")
    print()
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Create expert user
        user = create_expert_user(
            db=db,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_verified=is_verified
        )
        
        print("\n" + "=" * 60)
        print("✅ Expert User Creation Complete!")
        print("=" * 60)
        print("\nYou can now login with:")
        print(f"  Email: {email}")
        print(f"  Password: {password}")
        print(f"\nAccess Expert Dashboard at:")
        print(f"  http://localhost:3000/expert/dashboard")
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error creating expert user: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

