# Session Persistence Testing Guide

## Issue Fixed
The `/auth/me` endpoint returns `UserInfo` directly, but the frontend was expecting `{user: UserInfo}`. This mismatch caused the authentication initialization to fail, clearing tokens and logging users out on page refresh.

## What Was Changed

### File: `frontend/src/services/auth.service.ts`

**Before:**
```typescript
getCurrentUser: async (): Promise<UserInfoResponse> => {
  const response = await apiClient.get<UserInfoResponse>(
    `${AUTH_BASE_URL}/me`
  );
  
  return response.data;
},
```

**After:**
```typescript
getCurrentUser: async (): Promise<UserInfoResponse> => {
  const response = await apiClient.get<BackendUserInfo>(
    `${AUTH_BASE_URL}/me`
  );
  
  // The /auth/me endpoint returns UserInfo directly, not wrapped in {user: ...}
  // So we need to wrap it to match the UserInfoResponse interface
  return { user: response.data };
},
```

## Testing Steps

### Test 1: Login and Page Refresh (PRIMARY TEST)

1. **Clear browser data first:**
   - Open DevTools (F12)
   - Go to Application tab → Local Storage
   - Clear all items for `http://localhost:3000`
   - Close DevTools

2. **Login:**
   - Go to http://localhost:3000/login
   - Enter credentials:
     - Email: `testuser7@example.com`
     - Password: <PASSWORD_REDACTED>
   - Click "Sign in"
   - You should be redirected to the home page

3. **Check tokens are stored:**
   - Open DevTools (F12)
   - Go to Application tab → Local Storage → http://localhost:3000
   - You should see:
     - `access_token`: (long JWT string)
     - `refresh_token`: (long JWT string)

4. **Refresh the page:**
   - Press F5 or click browser refresh button
   - ✅ **EXPECTED: You should REMAIN LOGGED IN**
   - ❌ **BEFORE FIX: You would be logged out**

5. **Check console logs:**
   - Open Console tab in DevTools
   - You should see:
     ```
     [AuthContext] Initializing authentication...
     [AuthContext] Found tokens in localStorage
     [AuthContext] Fetching current user data...
     [AuthContext] User authenticated: testuser7@example.com
     [AuthContext] Initialization complete
     ```

### Test 2: Navigate and Refresh

1. After logging in, navigate to different pages:
   - Click on your username → "Profile Settings"
   - Refresh the page (F5)
   - ✅ You should remain on the profile page, still logged in

2. Navigate to Dashboard:
   - Click "Dashboard" in the menu
   - Refresh the page (F5)
   - ✅ You should remain on the dashboard, still logged in

3. Navigate to Subscription:
   - Click username → "Subscription"
   - Refresh the page (F5)
   - ✅ You should remain on the subscription page, still logged in

### Test 3: Logout and Refresh

1. Click username → "Logout"
2. You should be redirected to login page
3. Refresh the page (F5)
4. ✅ You should still be on the login page (not logged in)
5. Check Local Storage:
   - `access_token` and `refresh_token` should be GONE

### Test 4: Multiple Tabs

1. Login in Tab 1
2. Open a new tab (Tab 2) and go to http://localhost:3000
3. ✅ Tab 2 should automatically be logged in (same session)
4. Refresh Tab 2
5. ✅ Tab 2 should remain logged in
6. Logout in Tab 1
7. Refresh Tab 2
8. ✅ Tab 2 should redirect to login page

### Test 5: Close and Reopen Browser

1. Login to the application
2. Close the browser completely
3. Reopen the browser
4. Go to http://localhost:3000
5. ✅ You should still be logged in (tokens persist in localStorage)

## Debugging

### If session persistence still doesn't work:

1. **Check browser console for errors:**
   - Look for red error messages
   - Look for `[AuthContext]` log messages
   - Share any errors you see

2. **Check Network tab:**
   - Filter by "me" to see the `/auth/me` request
   - Check if it returns 200 OK or an error
   - Check the response body

3. **Check Local Storage:**
   - Verify tokens are actually being stored
   - Verify tokens are not being cleared unexpectedly

4. **Check backend logs:**
   - Look for any errors in the backend terminal
   - Check if `/auth/me` requests are being received

### Common Issues:

**Issue: "Not authenticated" error**
- Cause: Token is invalid or expired
- Solution: Clear localStorage and login again

**Issue: Tokens not found in localStorage**
- Cause: Login didn't complete successfully
- Solution: Check network tab for login request errors

**Issue: User data fetch fails**
- Cause: Backend endpoint mismatch or error
- Solution: Check backend logs and network response

## Expected Console Output

### On Login:
```
[AuthContext] Initializing authentication...
[AuthContext] No tokens found in localStorage
[AuthContext] Initialization complete
// ... login happens ...
```

### On Page Refresh (After Login):
```
[AuthContext] Initializing authentication...
[AuthContext] Found tokens in localStorage
[AuthContext] Fetching current user data...
[AuthContext] User authenticated: testuser7@example.com
[AuthContext] Initialization complete
```

### On Logout:
```
// Tokens cleared from localStorage
[AuthContext] Initializing authentication...
[AuthContext] No tokens found in localStorage
[AuthContext] Initialization complete
```

## Server Status

Make sure both servers are running:

```bash
# Check backend
curl http://localhost:8000/api/v1/health
# Should return: {"status":"healthy",...}

# Check frontend
curl http://localhost:3000
# Should return HTML content
```

## Summary

The fix ensures that:
1. ✅ Tokens are stored in localStorage on login
2. ✅ Tokens are retrieved from localStorage on page load
3. ✅ User data is fetched using the stored tokens
4. ✅ Session persists across page refreshes
5. ✅ Automatic token refresh works when access token expires
6. ✅ Logout properly clears tokens

The root cause was a data structure mismatch between what the backend returns and what the frontend expected. This has been fixed by wrapping the response in the correct format.

