# Email Service Documentation

## Overview

The Email Service is a reusable, provider-agnostic email sending system for the Soccer Predictions Platform. It supports multiple email providers (SMTP, SendGrid, AWS SES) and provides a clean API for sending transactional emails.

## Features

- ✅ **Multi-Provider Support**: SMTP, SendGrid (future), AWS SES (future)
- ✅ **Asynchronous Sending**: Non-blocking email delivery using background tasks
- ✅ **Template Engine**: Jinja2-based HTML and plain text templates
- ✅ **Fallback Content**: Automatic fallback when templates are unavailable
- ✅ **Error Handling**: Comprehensive error handling and logging
- ✅ **Provider-Agnostic**: Easy to switch between email providers
- ✅ **Environment-Based Configuration**: All credentials stored in environment variables

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Email Service Layer                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │     SMTP     │    │   SendGrid   │    │   AWS SES    │  │
│  │   Provider   │    │   Provider   │    │   Provider   │  │
│  │ (Implemented)│    │   (Future)   │    │   (Future)   │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                    │                    │         │
│         └────────────────────┴────────────────────┘         │
│                              │                              │
│                    ┌─────────▼─────────┐                    │
│                    │  Email Service    │                    │
│                    │   (Singleton)     │                    │
│                    └─────────┬─────────┘                    │
│                              │                              │
│                    ┌─────────▼─────────┐                    │
│                    │ Template Engine   │                    │
│                    │     (Jinja2)      │                    │
│                    └───────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

Add the following environment variables to your `.env` file:

```bash
# Email Configuration
EMAIL_PROVIDER=smtp                    # smtp, sendgrid, or ses
EMAIL_ENABLED=true                     # Enable/disable email sending

# SMTP Configuration (for Gmail, Mailtrap, etc.)
SMTP_HOST=smtp.gmail.com              # SMTP server hostname
SMTP_PORT=587                         # SMTP server port (587 for TLS, 465 for SSL)
SMTP_TLS=true                         # Use TLS encryption
SMTP_USER=your-email@gmail.com        # SMTP username
SMTP_PASSWORD=your-app-password       # SMTP password or app-specific password
EMAILS_FROM_EMAIL=noreply@yourplatform.com  # Sender email address
EMAILS_FROM_NAME=Soccer Predictions Platform  # Sender name

# Frontend URL (for email links)
FRONTEND_URL=http://localhost:3000    # Frontend application URL

# SendGrid Configuration (future use)
SENDGRID_API_KEY=your-sendgrid-api-key

# AWS SES Configuration (future use)
AWS_SES_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

### Provider-Specific Setup

#### SMTP (Gmail)

1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate App-Specific Password**:
   - Go to Google Account Settings → Security
   - Under "Signing in to Google", select "App passwords"
   - Generate a new app password for "Mail"
   - Use this password in `SMTP_PASSWORD`

3. **Configuration**:
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=true
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password
EMAILS_FROM_EMAIL=your-email@gmail.com
```

#### SMTP (Mailtrap - Development)

Mailtrap is recommended for local development and testing.

1. **Sign up** at https://mailtrap.io
2. **Get credentials** from your inbox settings
3. **Configuration**:
```bash
SMTP_HOST=smtp.mailtrap.io
SMTP_PORT=2525
SMTP_TLS=true
SMTP_USER=your-mailtrap-username
SMTP_PASSWORD=your-mailtrap-password
EMAILS_FROM_EMAIL=noreply@yourplatform.com
```

#### SendGrid (Future)

```bash
EMAIL_PROVIDER=sendgrid
SENDGRID_API_KEY=your-sendgrid-api-key
EMAILS_FROM_EMAIL=verified-sender@yourplatform.com
```

#### AWS SES (Future)

```bash
EMAIL_PROVIDER=ses
AWS_SES_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
EMAILS_FROM_EMAIL=verified-sender@yourplatform.com
```

## Usage

### Sending Welcome Email

The welcome email is automatically sent when a user registers:

```python
from app.services.email_service import email_service

# Send welcome email
success = await email_service.send_welcome_email(
    to_email="user@example.com",
    user_name="John Doe",
    user_id="123e4567-e89b-12d3-a456-426614174000"
)
```

### Sending Custom Email

```python
from app.services.email_service import email_service

# Send custom email
success = await email_service.send_email(
    to_email="recipient@example.com",
    subject="Your Custom Subject",
    html_content="<h1>Hello!</h1><p>This is a custom email.</p>",
    text_content="Hello! This is a custom email.",
    from_email="custom@example.com",  # Optional
    from_name="Custom Sender"          # Optional
)
```

### Using Background Tasks (Recommended)

To avoid blocking API responses, use FastAPI's BackgroundTasks:

```python
from fastapi import BackgroundTasks
from app.services.email_service import email_service

@router.post("/some-endpoint")
async def some_endpoint(background_tasks: BackgroundTasks):
    # Add email sending to background tasks
    background_tasks.add_task(
        email_service.send_welcome_email,
        to_email="user@example.com",
        user_name="John Doe",
        user_id="user-id"
    )
    
    return {"message": "Success"}
```

## Email Templates

### Template Structure

Templates are located in `backend/app/templates/emails/`:

```
backend/app/templates/emails/
├── welcome.html          # HTML version of welcome email
├── welcome.txt           # Plain text version of welcome email
├── password_reset.html   # (Future) Password reset email
└── password_reset.txt    # (Future) Password reset email
```

### Creating New Templates

1. **Create HTML template** (`your_template.html`):

```html
<!DOCTYPE html>
<html>
<head>
    <title>{{ subject }}</title>
</head>
<body>
    <h1>Hello {{ user_name }}!</h1>
    <p>{{ message }}</p>
    <a href="{{ action_url }}">Click Here</a>
</body>
</html>
```

2. **Create plain text template** (`your_template.txt`):

```text
Hello {{ user_name }}!

{{ message }}

Click here: {{ action_url }}
```

3. **Use the template**:

```python
# Render template
html_content = email_service.render_template('your_template.html', {
    'user_name': 'John Doe',
    'message': 'Your custom message',
    'action_url': 'https://example.com/action'
})

text_content = email_service.render_template('your_template.txt', {
    'user_name': 'John Doe',
    'message': 'Your custom message',
    'action_url': 'https://example.com/action'
})

# Send email
await email_service.send_email(
    to_email="user@example.com",
    subject="Your Subject",
    html_content=html_content,
    text_content=text_content
)
```

## Testing

### Running Tests

```bash
# Run all email service tests
cd backend
pytest tests/test_email_service.py -v

# Run with coverage
pytest tests/test_email_service.py --cov=app.services.email_service --cov-report=html
```

### Manual Testing

1. **Configure Mailtrap** for development
2. **Register a new user** via the API or frontend
3. **Check Mailtrap inbox** for the welcome email
4. **Verify email content** and links

### Test Email Sending

```python
# Test script
import asyncio
from app.services.email_service import email_service

async def test_email():
    success = await email_service.send_welcome_email(
        to_email="test@example.com",
        user_name="Test User",
        user_id="test-id"
    )
    print(f"Email sent: {success}")

asyncio.run(test_email())
```

## Error Handling

The email service includes comprehensive error handling:

- **Email sending failures** are logged but don't block the main operation
- **Template rendering errors** fall back to hardcoded content
- **Missing configuration** is detected and logged
- **Provider errors** are caught and logged with full stack traces

### Logging

All email operations are logged:

```python
# Success
logger.info(f"Email sent successfully to {to_email}")

# Warning
logger.warning(f"Failed to send welcome email to {to_email}")

# Error
logger.error(f"SMTP error sending email to {to_email}: {str(e)}", exc_info=True)
```

## Future Enhancements

### Planned Features

1. **Password Reset Emails** - Send password reset links
2. **Email Verification** - Send email verification links
3. **Notification Emails** - Prediction updates, subscription expiry, etc.
4. **SendGrid Integration** - Full SendGrid API support
5. **AWS SES Integration** - Full AWS SES support
6. **Email Queue** - Redis-based email queue for high volume
7. **Email Analytics** - Track open rates, click rates, etc.
8. **Email Preferences** - User-configurable email preferences
9. **Batch Sending** - Send emails to multiple recipients
10. **Email Attachments** - Support for file attachments

### Adding New Email Types

To add a new email type (e.g., password reset):

1. **Create templates**:
   - `backend/app/templates/emails/password_reset.html`
   - `backend/app/templates/emails/password_reset.txt`

2. **Add method to EmailService**:

```python
async def send_password_reset_email(
    self,
    to_email: str,
    user_name: str,
    reset_token: str
) -> bool:
    """Send password reset email"""
    context = {
        "user_name": user_name,
        "reset_url": f"{settings.FRONTEND_URL}/reset-password?token={reset_token}",
        "platform_name": "Soccer Predictions Platform",
        # ... other context variables
    }
    
    html_content = self.render_template("password_reset.html", context)
    text_content = self.render_template("password_reset.txt", context)
    
    return await self.send_email(
        to_email=to_email,
        subject="Reset Your Password",
        html_content=html_content,
        text_content=text_content
    )
```

3. **Use in endpoint**:

```python
@router.post("/forgot-password")
async def forgot_password(
    email: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    # ... generate reset token ...
    
    background_tasks.add_task(
        email_service.send_password_reset_email,
        to_email=email,
        user_name=user.first_name,
        reset_token=reset_token
    )
    
    return {"message": "Password reset email sent"}
```

## Troubleshooting

### Common Issues

**Issue**: Emails not being sent
- **Solution**: Check `EMAIL_ENABLED=true` in `.env`
- **Solution**: Verify SMTP credentials are correct
- **Solution**: Check backend logs for error messages

**Issue**: Gmail authentication failed
- **Solution**: Enable 2FA and use app-specific password
- **Solution**: Allow less secure apps (not recommended)

**Issue**: Templates not found
- **Solution**: Verify `EMAIL_TEMPLATES_DIR` path is correct
- **Solution**: Check templates exist in `backend/app/templates/emails/`
- **Solution**: Service will use fallback content if templates missing

**Issue**: Emails going to spam
- **Solution**: Use verified sender domain
- **Solution**: Configure SPF, DKIM, and DMARC records
- **Solution**: Use reputable email provider (SendGrid, AWS SES)

## Security Best Practices

1. **Never commit credentials** to version control
2. **Use environment variables** for all sensitive data
3. **Use app-specific passwords** for Gmail
4. **Rotate credentials** regularly
5. **Use TLS encryption** for SMTP connections
6. **Validate email addresses** before sending
7. **Rate limit** email sending to prevent abuse
8. **Monitor** email sending for suspicious activity

## Support

For issues or questions:
- Check backend logs: `backend/logs/`
- Review test results: `pytest tests/test_email_service.py -v`
- Contact: s92fotso@gmail.com

