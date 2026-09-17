# Email Service Testing Guide

## 🎯 Overview

This guide provides step-by-step instructions for testing the email service integration with the registration flow.

---

## ✅ Fixes Applied

### Issue 1: Email Not Being Sent (FIXED)
**Root Cause**: SMTP configuration was using `use_tls=True` for Mailtrap port 2525, which requires `start_tls` instead.

**Fix**: Updated `backend/app/services/email_service.py` to:
- Use `use_tls=True` for port 465 (direct TLS)
- Use `start_tls=True` for ports 587, 2525 (STARTTLS)

### Issue 2: Username Not Being Saved (FIXED)
**Root Cause**: Backend was hardcoding username from email prefix instead of using user-provided username.

**Fix**: 
1. Added `username` field to `RegisterRequest` schema (backend)
2. Updated registration endpoint to use provided username or fallback to email prefix
3. Updated frontend `RegisterRequest` interface to include `username` field
4. Updated `RegisterPage.tsx` to send username in registration request

---

## 📧 Email Configuration Options

You have **two options** for testing emails:

### Option 1: Mailtrap (Recommended for Testing)

**Pros**: 
- Safe testing environment (emails don't go to real inboxes)
- Easy to view all sent emails in one place
- No risk of spamming real email addresses

**Setup**:
1. Sign up for free at https://mailtrap.io
2. Go to "Email Testing" → "Inboxes" → "My Inbox"
3. Copy the SMTP credentials
4. Update `backend/.env`:

```bash
EMAIL_PROVIDER=smtp
EMAIL_ENABLED=true
SMTP_HOST=smtp.mailtrap.io
SMTP_PORT=2525
SMTP_TLS=true
SMTP_USER=your-mailtrap-username-here
SMTP_PASSWORD=your-mailtrap-password-here
EMAILS_FROM_EMAIL=noreply@soccerpredictions.com
EMAILS_FROM_NAME=Soccer Predictions Platform
FRONTEND_URL=http://localhost:3000
```

### Option 2: Gmail (For Real Email Testing)

**Pros**:
- Sends real emails to actual inboxes
- Tests the complete email delivery flow

**Setup**:
1. Enable 2-Factor Authentication on your Gmail account
2. Generate an App-Specific Password:
   - Go to https://myaccount.google.com/security
   - Click "2-Step Verification"
   - Scroll to "App passwords"
   - Generate a new app password for "Mail"
3. Update `backend/.env`:

```bash
EMAIL_PROVIDER=smtp
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=true
SMTP_USER=<email-redacted>
SMTP_PASSWORD=your-app-specific-password-here
EMAILS_FROM_EMAIL=<email-redacted>
EMAILS_FROM_NAME=Soccer Predictions Platform
FRONTEND_URL=http://localhost:3000
```

---

## 🚀 Testing Instructions

### Step 1: Configure Email Service

1. **Choose your email provider** (Mailtrap or Gmail)
2. **Update `backend/.env`** with the appropriate credentials (see above)
3. **Verify configuration**:
   ```bash
   cd backend
   cat .env | grep EMAIL
   cat .env | grep SMTP
   ```

### Step 2: Restart Backend Server

The backend server needs to be restarted to pick up the new `.env` configuration:

```bash
# Kill the current backend process (Ctrl+C in the terminal)
# Then restart:
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected Output**:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [xxxxx] using WatchFiles
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### Step 3: Verify Frontend is Running

```bash
cd frontend
npm run dev
```

**Expected Output**:
```
VITE v4.5.14  ready in 105 ms

➜  Local:   http://localhost:3000/
➜  Network: http://192.168.1.176:3000/
```

### Step 4: Test Registration Flow

1. **Open your browser** and navigate to:
   ```
   http://localhost:3000/register
   ```

2. **Fill in the registration form**:
   - **First Name**: Test
   - **Last Name**: User
   - **Email**: Use a real email address (e.g., `<email-redacted>`)
   - **Username**: Choose a unique username (e.g., `testuser123`)
   - **Password**: At least 8 characters (e.g., `password123`)
   - **Confirm Password**: Same as password
   - **Check**: "I agree to the terms and conditions"

3. **Click "Create account"**

### Step 5: Verify Registration Success

**Expected Frontend Behavior**:
- ✅ Registration succeeds
- ✅ User is redirected to home page (`/`)
- ✅ Toast notification shows: "Registration successful!"
- ✅ Second toast shows: "Account created successfully! Welcome email sent to your inbox."
- ✅ User is logged in automatically

**Expected Backend Logs** (check terminal):
```
INFO:     127.0.0.1:xxxxx - "POST /api/v1/auth/register HTTP/1.1" 201 Created
INFO:     Welcome email sent successfully to <email-redacted>
```

### Step 6: Check Email Delivery

#### If Using Mailtrap:
1. Go to https://mailtrap.io
2. Navigate to "Email Testing" → "Inboxes" → "My Inbox"
3. You should see the welcome email in the inbox
4. Click to view the email content

#### If Using Gmail:
1. Check your Gmail inbox
2. Look for an email from "Soccer Predictions Platform"
3. Subject: "Welcome to Soccer Predictions Platform!"

**Expected Email Content**:
- Professional HTML design with gradient header
- Personalized greeting: "Hi Test User,"
- Welcome message
- "Get Started" button linking to dashboard
- Footer with support email

### Step 7: Verify Username is Saved Correctly

1. **Check the database** (optional):
   ```bash
   docker exec -it soccer_predictions_db psql -U postgres -d soccer_predictions
   ```
   ```sql
   SELECT username, email, first_name, last_name FROM users.users ORDER BY created_at DESC LIMIT 1;
   ```
   
   **Expected Output**:
   ```
    username    |        email         | first_name | last_name
   -------------+----------------------+------------+-----------
    testuser123 | <email-redacted> | Test       | User
   ```

2. **Or check in the frontend**:
   - After registration, you should be logged in
   - Check the user profile or dashboard
   - Username should be `testuser123` (not `your-email` from email prefix)

---

## 🔍 Monitoring & Debugging

### What to Monitor

1. **Browser Console** (F12 → Console tab):
   - Should show no errors
   - Network tab should show `POST /api/v1/auth/register` returning `201 Created`

2. **Backend Logs** (terminal running backend):
   - Look for: `"Welcome email sent successfully to ..."`
   - If you see errors, check the SMTP configuration

3. **Network Requests** (F12 → Network tab):
   - `POST /api/v1/auth/register` should return:
     ```json
     {
       "access_token": "...",
       "refresh_token": "...",
       "token_type": "bearer",
       "user": {
         "id": "...",
         "email": "<email-redacted>",
         "username": "testuser123",
         "first_name": "Test",
         "last_name": "User",
         ...
       },
       "message": "User registered successfully"
     }
     ```

### Common Issues & Solutions

#### Issue: Email not received

**Check**:
1. Backend logs for SMTP errors
2. `.env` file has correct SMTP credentials
3. Backend server was restarted after updating `.env`
4. `EMAIL_ENABLED=true` in `.env`

**Solution**:
- For Mailtrap: Verify credentials from Mailtrap dashboard
- For Gmail: Ensure you're using an app-specific password, not your regular password

#### Issue: Username still showing email prefix

**Check**:
1. Frontend is sending `username` field in the request (check Network tab)
2. Backend schema includes `username` field
3. Both frontend and backend were reloaded after code changes

**Solution**:
- Clear browser cache and reload frontend
- Restart backend server
- Try registering with a new email address

#### Issue: "Passwords do not match" error

**Solution**: Make sure Password and Confirm Password fields have the same value

#### Issue: "Please agree to the terms and conditions"

**Solution**: Check the "I agree to the terms and conditions" checkbox

---

## 📊 Test Results Checklist

Use this checklist to verify everything is working:

- [ ] Backend server is running on http://localhost:8000
- [ ] Frontend server is running on http://localhost:3000
- [ ] Email configuration is set in `backend/.env`
- [ ] Registration form loads at http://localhost:3000/register
- [ ] Can fill in all form fields (first name, last name, email, username, password)
- [ ] Registration succeeds (201 Created response)
- [ ] User is redirected to home page after registration
- [ ] Toast notifications appear ("Registration successful!" and "Welcome email sent")
- [ ] User is automatically logged in after registration
- [ ] Welcome email is received (Mailtrap inbox or Gmail inbox)
- [ ] Email content is properly formatted (HTML with gradient design)
- [ ] Username in database matches user-provided username (not email prefix)
- [ ] Backend logs show "Welcome email sent successfully"

---

## 🎉 Success Criteria

The email service integration is working correctly if:

1. ✅ User can register with custom username
2. ✅ Username is saved correctly in database (not auto-generated from email)
3. ✅ Welcome email is sent asynchronously (doesn't block registration)
4. ✅ Email is received in Mailtrap or Gmail inbox
5. ✅ Email content is professional and properly formatted
6. ✅ Registration flow completes successfully
7. ✅ User is logged in automatically after registration

---

## 📝 Next Steps

After successful testing:

1. **Production Configuration**: Update `.env` for production with real SMTP provider (SendGrid, AWS SES, etc.)
2. **Email Templates**: Customize email templates in `backend/app/templates/emails/`
3. **Additional Email Features**: Implement password reset, email verification, etc.
4. **Monitoring**: Set up email delivery monitoring and error tracking

---

## 🆘 Need Help?

If you encounter issues:

1. Check backend logs for detailed error messages
2. Verify SMTP credentials are correct
3. Ensure backend server was restarted after `.env` changes
4. Test SMTP connection manually using the test script:
   ```bash
   cd backend
   python test_email_manual.py
   ```

---

**Last Updated**: 2025-10-10
**Status**: Ready for Testing ✅

