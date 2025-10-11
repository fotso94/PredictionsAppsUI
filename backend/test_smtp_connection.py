#!/usr/bin/env python3
"""
Test SMTP connection to verify email credentials
"""
import asyncio
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

async def test_smtp_connection():
    """Test SMTP connection with Mailtrap Live credentials"""
    
    # Mailtrap Live credentials
    smtp_host = "live.smtp.mailtrap.io"
    smtp_port = 587
    smtp_user = "api"
    smtp_password = "e839cb17caf5bfbd9a1ba2779d8ec68f"
    from_email = "hello@camerinfrabeauty.com"
    to_email = "fotsostephan88@gmail.com"
    
    print(f"Testing SMTP connection to {smtp_host}:{smtp_port}")
    print(f"Username: {smtp_user}")
    print(f"From: {from_email}")
    print(f"To: {to_email}")
    print("-" * 50)
    
    # Create message
    message = MIMEMultipart("alternative")
    message["Subject"] = "Test Email from Soccer Predictions Platform"
    message["From"] = from_email
    message["To"] = to_email
    
    text_content = "This is a test email to verify SMTP configuration."
    html_content = "<html><body><h1>Test Email</h1><p>This is a test email to verify SMTP configuration.</p></body></html>"
    
    message.attach(MIMEText(text_content, "plain"))
    message.attach(MIMEText(html_content, "html"))
    
    try:
        print("Attempting to send email...")
        
        # Try with STARTTLS
        await aiosmtplib.send(
            message,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user,
            password=smtp_password,
            start_tls=True
        )
        
        print("✅ Email sent successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_smtp_connection())
    exit(0 if result else 1)

