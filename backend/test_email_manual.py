"""
Manual Email Service Test Script

This script demonstrates the email service functionality.
Configure your email settings in .env before running.

Usage:
    python test_email_manual.py
"""

import asyncio
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.email_service import email_service
from app.core.config import settings


async def test_email_service():
    """Test the email service"""
    
    print("=" * 80)
    print("Email Service Test")
    print("=" * 80)
    print()
    
    # Check configuration
    print("Configuration:")
    print(f"  Provider: {settings.EMAIL_PROVIDER}")
    print(f"  Enabled: {settings.EMAIL_ENABLED}")
    print(f"  SMTP Host: {settings.SMTP_HOST or 'Not configured'}")
    print(f"  SMTP Port: {settings.SMTP_PORT}")
    print(f"  From Email: {settings.EMAILS_FROM_EMAIL or 'Not configured'}")
    print(f"  From Name: {settings.EMAILS_FROM_NAME}")
    print()
    
    # Check if email is configured
    if not settings.SMTP_HOST or not settings.EMAILS_FROM_EMAIL:
        print("⚠️  Email not configured!")
        print()
        print("To configure email, add the following to your .env file:")
        print()
        print("# For Mailtrap (Development)")
        print("EMAIL_PROVIDER=smtp")
        print("EMAIL_ENABLED=true")
        print("SMTP_HOST=smtp.mailtrap.io")
        print("SMTP_PORT=2525")
        print("SMTP_USER=your-mailtrap-username")
        print("SMTP_PASSWORD=your-mailtrap-password")
        print("EMAILS_FROM_EMAIL=noreply@soccerpredictions.com")
        print("FRONTEND_URL=http://localhost:3000")
        print()
        print("# For Gmail")
        print("EMAIL_PROVIDER=smtp")
        print("EMAIL_ENABLED=true")
        print("SMTP_HOST=smtp.gmail.com")
        print("SMTP_PORT=587")
        print("SMTP_TLS=true")
        print("SMTP_USER=your-email@gmail.com")
        print("SMTP_PASSWORD=your-app-specific-password")
        print("EMAILS_FROM_EMAIL=your-email@gmail.com")
        print("FRONTEND_URL=http://localhost:3000")
        print()
        return
    
    # Get recipient email
    print("Enter recipient email address:")
    to_email = input("> ").strip()
    
    if not to_email:
        print("❌ No email address provided")
        return
    
    print()
    print(f"Sending welcome email to: {to_email}")
    print()
    
    # Send welcome email
    try:
        success = await email_service.send_welcome_email(
            to_email=to_email,
            user_name="Test User",
            user_id="test-user-id-12345"
        )
        
        if success:
            print("✅ Email sent successfully!")
            print()
            print("Check your inbox (or Mailtrap) for the welcome email.")
        else:
            print("❌ Failed to send email")
            print()
            print("Check the logs above for error details.")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print()
    print("=" * 80)


async def test_custom_email():
    """Test sending a custom email"""
    
    print()
    print("=" * 80)
    print("Custom Email Test")
    print("=" * 80)
    print()
    
    # Get recipient email
    print("Enter recipient email address:")
    to_email = input("> ").strip()
    
    if not to_email:
        print("❌ No email address provided")
        return
    
    print()
    print("Enter email subject:")
    subject = input("> ").strip() or "Test Email"
    
    print()
    print("Enter email message:")
    message = input("> ").strip() or "This is a test email from the Soccer Predictions Platform."
    
    print()
    print(f"Sending custom email to: {to_email}")
    print()
    
    # Create HTML content
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background: #f8f9fa; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>⚽ Soccer Predictions Platform</h1>
            </div>
            <div class="content">
                <h2>{subject}</h2>
                <p>{message}</p>
                <p>This is a test email sent from the email service.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Create plain text content
    text_content = f"""
    ⚽ Soccer Predictions Platform
    
    {subject}
    
    {message}
    
    This is a test email sent from the email service.
    """
    
    # Send email
    try:
        success = await email_service.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )
        
        if success:
            print("✅ Email sent successfully!")
            print()
            print("Check your inbox (or Mailtrap) for the email.")
        else:
            print("❌ Failed to send email")
            print()
            print("Check the logs above for error details.")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print()
    print("=" * 80)


async def main():
    """Main function"""
    
    print()
    print("Email Service Test Script")
    print()
    print("Choose test type:")
    print("1. Send welcome email")
    print("2. Send custom email")
    print("3. Exit")
    print()
    
    choice = input("Enter choice (1-3): ").strip()
    
    if choice == "1":
        await test_email_service()
    elif choice == "2":
        await test_custom_email()
    elif choice == "3":
        print("Exiting...")
        return
    else:
        print("Invalid choice")


if __name__ == "__main__":
    asyncio.run(main())

