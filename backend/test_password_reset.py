#!/usr/bin/env python3
"""
Test script for password reset functionality
Tests the complete password reset flow
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def test_forgot_password(email):
    """Test the forgot password endpoint"""
    print_section("TEST 1: Request Password Reset")
    
    url = f"{BASE_URL}/auth/forgot-password"
    payload = {"email": email}
    
    print(f"📧 Requesting password reset for: {email}")
    print(f"🔗 POST {url}")
    print(f"📦 Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(url, json=payload)
        print(f"\n✅ Status Code: {response.status_code}")
        print(f"📄 Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("\n✅ SUCCESS: Password reset email sent!")
            print("📧 Check your email inbox for the reset link")
            print("📋 Check backend logs (Terminal 124) for the reset token")
            return True
        else:
            print(f"\n❌ FAILED: Unexpected status code {response.status_code}")
            return False
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return False

def test_verify_token(token):
    """Test the verify reset token endpoint"""
    print_section("TEST 2: Verify Reset Token")
    
    url = f"{BASE_URL}/auth/verify-reset-token/{token}"
    
    print(f"🔑 Verifying token: {token[:20]}...")
    print(f"🔗 GET {url}")
    
    try:
        response = requests.get(url)
        print(f"\n✅ Status Code: {response.status_code}")
        print(f"📄 Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("\n✅ SUCCESS: Token is valid!")
            return True
        else:
            print(f"\n❌ FAILED: Token is invalid or expired")
            return False
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return False

def test_reset_password(token, new_password):
    """Test the reset password endpoint"""
    print_section("TEST 3: Reset Password")
    
    url = f"{BASE_URL}/auth/reset-password"
    payload = {
        "token": token,
        "new_password": new_password
    }
    
    print(f"🔑 Using token: {token[:20]}...")
    print(f"🔒 New password: {'*' * len(new_password)}")
    print(f"🔗 POST {url}")
    
    try:
        response = requests.post(url, json=payload)
        print(f"\n✅ Status Code: {response.status_code}")
        print(f"📄 Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("\n✅ SUCCESS: Password reset successful!")
            print("📧 Check your email for confirmation")
            print("🔐 All user sessions have been revoked")
            print("🔑 You can now log in with the new password")
            return True
        else:
            print(f"\n❌ FAILED: Password reset failed")
            return False
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return False

def test_invalid_token():
    """Test with an invalid token"""
    print_section("TEST 4: Invalid Token Test")
    
    invalid_token = "invalid-token-12345"
    url = f"{BASE_URL}/auth/verify-reset-token/{invalid_token}"
    
    print(f"🔑 Testing with invalid token: {invalid_token}")
    print(f"🔗 GET {url}")
    
    try:
        response = requests.get(url)
        print(f"\n✅ Status Code: {response.status_code}")
        print(f"📄 Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 400:
            print("\n✅ SUCCESS: Invalid token correctly rejected!")
            return True
        else:
            print(f"\n❌ FAILED: Expected 400 status code")
            return False
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return False

def main():
    """Main test function"""
    print("\n" + "🔐"*30)
    print("  PASSWORD RESET FUNCTIONALITY TEST")
    print("🔐"*30)
    
    # Test 1: Request password reset
    print("\n📝 Enter the email address to test with:")
    print("   (Use a registered email, e.g., fotsostephan88@gmail.com)")
    email = input("   Email: ").strip()
    
    if not email:
        print("❌ Email is required!")
        return
    
    success = test_forgot_password(email)
    
    if not success:
        print("\n❌ Test failed. Exiting.")
        return
    
    # Test 4: Invalid token test
    test_invalid_token()
    
    # Test 2 & 3: Verify and reset (requires manual token input)
    print("\n" + "="*60)
    print("📋 NEXT STEPS:")
    print("="*60)
    print("1. Check your email inbox for the password reset email")
    print("2. Copy the reset token from the email or backend logs")
    print("3. Run this script again with the token to test verification and reset")
    print("\nOR")
    print("1. Click the reset link in the email")
    print("2. Test the complete flow through the UI at http://localhost:3000")
    print("="*60)
    
    # Optional: Test with token if provided
    print("\n📝 Do you have a reset token to test? (y/n)")
    has_token = input("   ").strip().lower()
    
    if has_token == 'y':
        print("\n📝 Enter the reset token:")
        token = input("   Token: ").strip()
        
        if token:
            # Test verify token
            if test_verify_token(token):
                # Test reset password
                print("\n📝 Enter new password (min 8 characters):")
                new_password = input("   Password: ").strip()
                
                if len(new_password) >= 8:
                    test_reset_password(token, new_password)
                else:
                    print("❌ Password must be at least 8 characters!")
    
    print("\n" + "🎉"*30)
    print("  TEST COMPLETE!")
    print("🎉"*30)
    print("\n")

if __name__ == "__main__":
    main()

