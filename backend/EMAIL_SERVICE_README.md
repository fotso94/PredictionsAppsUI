# Email Service - Quick Start Guide

## Overview

The Email Service is a reusable, production-ready email system for the Soccer Predictions Platform. It automatically sends welcome emails when users register and can be easily extended for other email types.

## Quick Setup

### 1. Choose Your Email Provider

#### Option A: Mailtrap (Recommended for Development)

Mailtrap is a fake SMTP server for testing emails without sending them to real users.

1. Sign up at https://mailtrap.io (free)
2. Go to your inbox and copy the SMTP credentials
3. Add to your `.env` file:

```bash
EMAIL_PROVIDER=smtp
EMAIL_ENABLED=true
SMTP_HOST=smtp.mailtrap.io
SMTP_PORT=2525
SMTP_USER=your-mailtrap-username
SMTP_PASSWORD=your-mailtrap-password
EMAILS_FROM_EMAIL=noreply@soccerpredictions.com
EMAILS_FROM_NAME=Soccer Predictions Platform
FRONTEND_URL=http://localhost:3000
```

#### Option B: Gmail (For Real Emails)

1. Enable 2-Factor Authentication on your Gmail account
2. Generate an app-specific password:
   - Go to Google Account → Security → App passwords
   - Generate password for "Mail"
3. Add to your `.env` file:

```bash
EMAIL_PROVIDER=smtp
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=true
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password
EMAILS_FROM_EMAIL=your-email@gmail.com
EMAILS_FROM_NAME=Soccer Predictions Platform
FRONTEND_URL=http://localhost:3000
```

### 2. Install Dependencies

```bash
cd backend
pip install jinja2==3.1.2 aiosmtplib==3.0.1
```

### 3. Test the Email Service

#### Run Unit Tests

```bash
cd backend
pytest tests/test_email_service.py -v
```

Expected output:
```
15 passed, 15 warnings in 0.51s
Coverage: 86%
```

#### Manual Test

```bash
cd backend
python test_email_manual.py
```

This interactive script will:
1. Check your email configuration
2. Let you send a test welcome email
3. Let you send a custom email

### 4. Test Registration Flow

#### Start the Backend

```bash
cd backend
uvicorn app.main:app --reload
```

#### Register a New User

**Via API**:
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123",
    "first_name": "Test",
    "last_name": "User",
    "role": "regular"
  }'
```

**Via Frontend**:
1. Go to http://localhost:3000/register
2. Fill in the registration form
3. Submit

#### Check Your Email

- **Mailtrap**: Go to https://mailtrap.io and check your inbox
- **Gmail**: Check your Gmail inbox

You should receive a professional welcome email with:
- Personalized greeting
- Platform features overview
- Call-to-action button (Go to Dashboard)
- Quick links
- Support information

## How It Works

### Registration Flow

```
User Registers
     │
     ▼
Create User Account
     │
     ▼
Generate Auth Tokens
     │
     ▼
Add Email to Background Tasks ← Non-blocking!
     │
     ▼
Return Success Response
     │
     ▼
(Background) Send Welcome Email
```

**Key Points**:
- Email sending is **asynchronous** (doesn't block registration)
- Email failures **don't prevent** user registration
- All email operations are **logged**

### Email Templates

Templates are located in `backend/app/templates/emails/`:

- `welcome.html` - Beautiful HTML email with gradient design
- `welcome.txt` - Plain text version for email clients without HTML support

Templates use Jinja2 for dynamic content:
```html
<h1>Welcome, {{ user_name }}!</h1>
<a href="{{ dashboard_url }}">Go to Dashboard</a>
```

## Usage in Code

### Send Welcome Email

```python
from app.services.email_service import email_service
from fastapi import BackgroundTasks

@router.post("/register")
async def register(
    background_tasks: BackgroundTasks,
    # ... other parameters
):
    # ... create user ...
    
    # Send welcome email asynchronously
    background_tasks.add_task(
        email_service.send_welcome_email,
        to_email=user.email,
        user_name=user.full_name,
        user_id=str(user.id)
    )
    
    return {"message": "Registration successful"}
```

### Send Custom Email

```python
from app.services.email_service import email_service

# Send custom email
success = await email_service.send_email(
    to_email="user@example.com",
    subject="Your Custom Subject",
    html_content="<h1>Hello!</h1><p>Custom message</p>",
    text_content="Hello! Custom message",
    from_email="custom@example.com",  # Optional
    from_name="Custom Sender"          # Optional
)
```

## Configuration Reference

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `EMAIL_PROVIDER` | Email provider (smtp, sendgrid, ses) | `smtp` |
| `EMAIL_ENABLED` | Enable/disable email sending | `true` |
| `SMTP_HOST` | SMTP server hostname | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP server port | `587` |
| `SMTP_TLS` | Use TLS encryption | `true` |
| `SMTP_USER` | SMTP username | `user@gmail.com` |
| `SMTP_PASSWORD` | SMTP password | `app-password` |
| `EMAILS_FROM_EMAIL` | Sender email address | `noreply@example.com` |
| `EMAILS_FROM_NAME` | Sender name | `Platform Name` |
| `FRONTEND_URL` | Frontend URL for links | `http://localhost:3000` |

### Disable Email Sending

To disable email sending (e.g., during testing):

```bash
EMAIL_ENABLED=false
```

Emails will be logged but not sent.

## Troubleshooting

### Issue: Emails not being sent

**Check**:
1. `EMAIL_ENABLED=true` in `.env`
2. SMTP credentials are correct
3. Backend logs for error messages

**Solution**:
```bash
# Check backend logs
tail -f backend/logs/app.log

# Or run backend in debug mode
cd backend
uvicorn app.main:app --reload --log-level debug
```

### Issue: Gmail authentication failed

**Solutions**:
1. Enable 2-Factor Authentication
2. Generate app-specific password (not your regular password)
3. Allow less secure apps (not recommended)

### Issue: Templates not found

**Check**:
1. Templates exist in `backend/app/templates/emails/`
2. `EMAIL_TEMPLATES_DIR` is correct in config

**Note**: Service will use fallback content if templates are missing.

### Issue: Emails going to spam

**Solutions**:
1. Use verified sender domain
2. Configure SPF, DKIM, and DMARC records
3. Use reputable email provider (SendGrid, AWS SES)

## Testing

### Unit Tests

```bash
cd backend
pytest tests/test_email_service.py -v --cov=app.services.email_service
```

### Manual Testing

```bash
cd backend
python test_email_manual.py
```

### Integration Testing

```bash
# Start backend
cd backend
uvicorn app.main:app --reload

# In another terminal, register a user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123",
    "first_name": "Test",
    "last_name": "User",
    "role": "regular"
  }'

# Check Mailtrap or Gmail for welcome email
```

## Future Features

The email service is designed to be easily extended:

1. **Password Reset** - Send password reset links
2. **Email Verification** - Send email verification links
3. **Notifications** - Prediction updates, subscription expiry
4. **SendGrid** - Full SendGrid API support
5. **AWS SES** - Full AWS SES support
6. **Email Queue** - Redis-based queue for high volume
7. **Analytics** - Track open rates, click rates
8. **Preferences** - User email preferences

## Documentation

- **Full Documentation**: `backend/docs/EMAIL_SERVICE_DOCUMENTATION.md`
- **Implementation Summary**: `backend/EMAIL_SERVICE_IMPLEMENTATION_SUMMARY.md`
- **Configuration Examples**: `backend/.env.example`

## Support

For issues or questions:
- Check backend logs
- Review test results
- See full documentation
- Contact: s92fotso@gmail.com

## Summary

✅ **Email service is production-ready**  
✅ **86% test coverage**  
✅ **Comprehensive documentation**  
✅ **Easy to configure and use**  
✅ **Extensible for future features**

Happy emailing! 📧⚽

