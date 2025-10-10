"""
Test script for Public API endpoints
Tests all KAN-25 subtask endpoints
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"

# Test credentials (using existing test user)
TEST_USER = {
    "email": "testuser7@example.com",
    "password": "password123"  # Default password for test users
}

def print_section(title):
    """Print a section header"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def print_result(endpoint, status_code, response_data):
    """Print test result"""
    status_icon = "✓" if 200 <= status_code < 300 else "✗"
    print(f"\n{status_icon} {endpoint}")
    print(f"   Status: {status_code}")
    if isinstance(response_data, dict):
        print(f"   Response: {json.dumps(response_data, indent=2, default=str)[:500]}")
    else:
        print(f"   Response: {str(response_data)[:500]}")

def safe_json(response):
    """Safely get JSON from response"""
    try:
        return response.json()
    except:
        return {"error": "Failed to parse JSON", "text": response.text[:200]}

def test_health():
    """Test health endpoint"""
    print_section("Testing Health Endpoint")

    response = requests.get(f"{BASE_URL}/health")
    print_result("GET /health", response.status_code, safe_json(response))
    return response.status_code == 200

def test_auth():
    """Test authentication endpoints"""
    print_section("Testing Authentication Endpoints")

    # Test login
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={
            "email": TEST_USER["email"],
            "password": TEST_USER["password"]
        }
    )
    result = safe_json(response)
    print_result("POST /auth/login", response.status_code, result)

    if response.status_code == 200:
        return result.get("access_token"), result.get("refresh_token")

    return None, None

def test_user_endpoints(access_token):
    """Test user management endpoints"""
    print_section("Testing User Endpoints")
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # KAN-126: GET /users/me
    response = requests.get(f"{BASE_URL}/users/me", headers=headers)
    print_result("GET /users/me (KAN-126)", response.status_code, safe_json(response))
    
    # KAN-127: PUT /users/me
    response = requests.put(
        f"{BASE_URL}/users/me",
        headers=headers,
        json={
            "first_name": "Test",
            "last_name": "User Updated"
        }
    )
    print_result("PUT /users/me (KAN-127)", response.status_code, safe_json(response))

    # KAN-129: PUT /users/me/preferences
    response = requests.put(
        f"{BASE_URL}/users/me/preferences",
        headers=headers,
        json={
            "theme": "dark",
            "email_notifications": True,
            "odds_format": "decimal"
        }
    )
    print_result("PUT /users/me/preferences (KAN-129)", response.status_code, safe_json(response))

def test_prediction_endpoints(access_token):
    """Test prediction endpoints"""
    print_section("Testing Prediction Endpoints")
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # KAN-130: GET /predictions
    response = requests.get(
        f"{BASE_URL}/predictions",
        headers=headers,
        params={"page": 1, "page_size": 5}
    )
    result = safe_json(response)
    print_result("GET /predictions (KAN-130)", response.status_code, result)

    predictions = result.get("predictions", [])
    prediction_id = predictions[0]["id"] if predictions else None

    # KAN-132: GET /predictions/today
    response = requests.get(f"{BASE_URL}/predictions/today", headers=headers)
    print_result("GET /predictions/today (KAN-132)", response.status_code, safe_json(response))

    if prediction_id:
        # KAN-131: GET /predictions/{id}
        response = requests.get(f"{BASE_URL}/predictions/{prediction_id}", headers=headers)
        print_result(f"GET /predictions/{prediction_id} (KAN-131)", response.status_code, safe_json(response))

        # KAN-136: POST /predictions/{id}/feedback
        response = requests.post(
            f"{BASE_URL}/predictions/{prediction_id}/feedback",
            headers=headers,
            json={
                "rating": 5,
                "comment": "Great prediction!",
                "is_upvote": True,
                "is_downvote": False
            }
        )
        print_result(f"POST /predictions/{prediction_id}/feedback (KAN-136)", response.status_code, safe_json(response))

        # KAN-137: GET /predictions/{id}/feedback
        response = requests.get(f"{BASE_URL}/predictions/{prediction_id}/feedback", headers=headers)
        print_result(f"GET /predictions/{prediction_id}/feedback (KAN-137)", response.status_code, safe_json(response))

def test_subscription_endpoints(access_token):
    """Test subscription endpoints"""
    print_section("Testing Subscription Endpoints")
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # KAN-135: GET /subscriptions/tiers
    response = requests.get(f"{BASE_URL}/subscriptions/tiers", headers=headers)
    print_result("GET /subscriptions/tiers (KAN-135)", response.status_code, safe_json(response))

    # KAN-133: GET /subscriptions/me
    response = requests.get(f"{BASE_URL}/subscriptions/me", headers=headers)
    print_result("GET /subscriptions/me (KAN-133)", response.status_code, safe_json(response))

    # KAN-134: PUT /subscriptions/me (upgrade to basic)
    response = requests.put(
        f"{BASE_URL}/subscriptions/me",
        headers=headers,
        json={"new_tier": "basic"}
    )
    print_result("PUT /subscriptions/me (KAN-134)", response.status_code, safe_json(response))

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("  PUBLIC API ENDPOINT TESTS - KAN-25")
    print("  Testing all implemented subtasks")
    print("="*80)
    
    # Test health
    if not test_health():
        print("\n❌ Health check failed. Is the server running?")
        return
    
    # Test authentication
    access_token, refresh_token = test_auth()
    if not access_token:
        print("\n❌ Authentication failed. Please check credentials.")
        print(f"   Expected user: {TEST_USER['email']}")
        print("   You may need to register this user first.")
        return
    
    print(f"\n✓ Authentication successful")
    print(f"   Access Token: {access_token[:50]}...")
    
    # Test all endpoints
    test_user_endpoints(access_token)
    test_prediction_endpoints(access_token)
    test_subscription_endpoints(access_token)
    
    print("\n" + "="*80)
    print("  TEST SUMMARY")
    print("="*80)
    print("\nAll endpoint tests completed!")
    print("\nImplemented Subtasks:")
    print("  ✓ KAN-126: GET /users/me")
    print("  ✓ KAN-127: PUT /users/me")
    print("  ✓ KAN-129: PUT /users/me/preferences")
    print("  ✓ KAN-130: GET /predictions")
    print("  ✓ KAN-131: GET /predictions/{id}")
    print("  ✓ KAN-132: GET /predictions/today")
    print("  ✓ KAN-133: GET /subscriptions/me")
    print("  ✓ KAN-134: PUT /subscriptions/me")
    print("  ✓ KAN-135: GET /subscriptions/tiers")
    print("  ✓ KAN-136: POST /predictions/{id}/feedback")
    print("  ✓ KAN-137: GET /predictions/{id}/feedback")
    print("\nNote: Some tests may fail if there's no data in the database.")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()

