"""
Email Service
Reusable email service for sending notifications
Supports SMTP, SendGrid, and AWS SES
"""

import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import ssl

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """
    Email service for sending emails via SMTP, SendGrid, or AWS SES
    """
    
    def __init__(self):
        """Initialize email service"""
        self.provider = settings.EMAIL_PROVIDER
        self.enabled = settings.EMAIL_ENABLED
        
        # Initialize Jinja2 template environment
        template_dir = Path(settings.EMAIL_TEMPLATES_DIR)
        if template_dir.exists():
            self.jinja_env = Environment(
                loader=FileSystemLoader(str(template_dir)),
                autoescape=select_autoescape(['html', 'xml'])
            )
        else:
            logger.warning(f"Email templates directory not found: {template_dir}")
            self.jinja_env = None
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None
    ) -> bool:
        """
        Send an email
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email content
            text_content: Plain text email content (optional)
            from_email: Sender email address (optional, uses default if not provided)
            from_name: Sender name (optional, uses default if not provided)
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.enabled:
            logger.info(f"Email service disabled. Would have sent email to {to_email}")
            return True
        
        try:
            if self.provider == "smtp":
                return await self._send_via_smtp(
                    to_email, subject, html_content, text_content, from_email, from_name
                )
            elif self.provider == "sendgrid":
                return await self._send_via_sendgrid(
                    to_email, subject, html_content, text_content, from_email, from_name
                )
            elif self.provider == "ses":
                return await self._send_via_ses(
                    to_email, subject, html_content, text_content, from_email, from_name
                )
            else:
                logger.error(f"Unknown email provider: {self.provider}")
                return False
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}", exc_info=True)
            return False
    
    async def _send_via_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None
    ) -> bool:
        """Send email via SMTP"""
        try:
            # Use default sender if not provided
            sender_email = from_email or settings.EMAILS_FROM_EMAIL
            sender_name = from_name or settings.EMAILS_FROM_NAME
            
            if not sender_email:
                logger.error("No sender email configured")
                return False
            
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{sender_name} <{sender_email}>" if sender_name else sender_email
            message["To"] = to_email
            
            # Add plain text part
            if text_content:
                text_part = MIMEText(text_content, "plain")
                message.attach(text_part)
            
            # Add HTML part
            html_part = MIMEText(html_content, "html")
            message.attach(html_part)
            
            # Send email
            # For Mailtrap port 2525, use STARTTLS instead of direct TLS
            # For Gmail port 587, use STARTTLS
            # For port 465, use direct TLS (use_tls=True)
            if settings.SMTP_PORT == 465:
                # Direct TLS connection
                await aiosmtplib.send(
                    message,
                    hostname=settings.SMTP_HOST,
                    port=settings.SMTP_PORT,
                    username=settings.SMTP_USER,
                    password=settings.SMTP_PASSWORD,
                    use_tls=True
                )
            else:
                # STARTTLS connection (ports 587, 2525, etc.)
                await aiosmtplib.send(
                    message,
                    hostname=settings.SMTP_HOST,
                    port=settings.SMTP_PORT,
                    username=settings.SMTP_USER,
                    password=settings.SMTP_PASSWORD,
                    start_tls=settings.SMTP_TLS
                )
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"SMTP error sending email to {to_email}: {str(e)}", exc_info=True)
            return False
    
    async def _send_via_sendgrid(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None
    ) -> bool:
        """Send email via SendGrid (placeholder for future implementation)"""
        logger.warning("SendGrid integration not yet implemented")
        return False
    
    async def _send_via_ses(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None
    ) -> bool:
        """Send email via AWS SES (placeholder for future implementation)"""
        logger.warning("AWS SES integration not yet implemented")
        return False
    
    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render an email template
        
        Args:
            template_name: Name of the template file
            context: Template context variables
            
        Returns:
            str: Rendered template content
        """
        if not self.jinja_env:
            raise ValueError("Template environment not initialized")
        
        template = self.jinja_env.get_template(template_name)
        return template.render(**context)
    
    async def send_welcome_email(
        self,
        to_email: str,
        user_name: str,
        user_id: str
    ) -> bool:
        """
        Send welcome email to new user
        
        Args:
            to_email: User's email address
            user_name: User's full name
            user_id: User's ID
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Prepare template context
            context = {
                "user_name": user_name or "there",
                "platform_name": "Soccer Predictions Platform",
                "frontend_url": settings.FRONTEND_URL,
                "login_url": f"{settings.FRONTEND_URL}/login",
                "dashboard_url": f"{settings.FRONTEND_URL}/dashboard",
                "support_email": settings.EMAILS_FROM_EMAIL,
                "year": 2025
            }
            
            # Render templates
            if self.jinja_env:
                try:
                    html_content = self.render_template("welcome.html", context)
                    text_content = self.render_template("welcome.txt", context)
                except Exception as e:
                    logger.warning(f"Failed to render template: {e}. Using fallback content.")
                    html_content = self._get_fallback_welcome_html(context)
                    text_content = self._get_fallback_welcome_text(context)
            else:
                html_content = self._get_fallback_welcome_html(context)
                text_content = self._get_fallback_welcome_text(context)
            
            # Send email
            return await self.send_email(
                to_email=to_email,
                subject=f"Welcome to {context['platform_name']}!",
                html_content=html_content,
                text_content=text_content
            )
            
        except Exception as e:
            logger.error(f"Failed to send welcome email to {to_email}: {str(e)}", exc_info=True)
            return False
    
    def _get_fallback_welcome_html(self, context: Dict[str, Any]) -> str:
        """Get fallback HTML content for welcome email"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Welcome to {context['platform_name']}</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px;">
                <h1 style="color: #2c3e50; margin-bottom: 20px;">Welcome to {context['platform_name']}!</h1>
                <p>Hi {context['user_name']},</p>
                <p>Thank you for joining {context['platform_name']}! We're excited to have you on board.</p>
                <p>With your account, you can:</p>
                <ul>
                    <li>Access expert soccer predictions</li>
                    <li>Track prediction history and performance</li>
                    <li>Manage your subscription and preferences</li>
                    <li>Get real-time match updates</li>
                </ul>
                <p style="margin-top: 30px;">
                    <a href="{context['dashboard_url']}" style="background-color: #3498db; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Go to Dashboard
                    </a>
                </p>
                <p style="margin-top: 30px; font-size: 14px; color: #666;">
                    If you have any questions, feel free to contact us at {context['support_email']}.
                </p>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="font-size: 12px; color: #999; text-align: center;">
                    &copy; {context['year']} {context['platform_name']}. All rights reserved.
                </p>
            </div>
        </body>
        </html>
        """
    
    def _get_fallback_welcome_text(self, context: Dict[str, Any]) -> str:
        """Get fallback plain text content for welcome email"""
        return f"""
Welcome to {context['platform_name']}!

Hi {context['user_name']},

Thank you for joining {context['platform_name']}! We're excited to have you on board.

With your account, you can:
- Access expert soccer predictions
- Track prediction history and performance
- Manage your subscription and preferences
- Get real-time match updates

Get started: {context['dashboard_url']}

If you have any questions, feel free to contact us at {context['support_email']}.

---
© {context['year']} {context['platform_name']}. All rights reserved.
        """

    async def send_password_reset_email(
        self,
        to_email: str,
        user_name: str,
        reset_token: str
    ) -> bool:
        """
        Send password reset email with reset link

        Args:
            to_email: Recipient email address
            user_name: User's name
            reset_token: Password reset token

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Build reset URL
            reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"

            # Prepare template context
            context = {
                'user_name': user_name,
                'reset_url': reset_url,
                'reset_token': reset_token,
                'platform_name': 'Soccer Predictions Platform',
                'support_email': 'support@soccerpredictions.com',
                'year': '2025'
            }

            # Render templates
            if self.jinja_env:
                try:
                    html_template = self.jinja_env.get_template('emails/password_reset.html')
                    text_template = self.jinja_env.get_template('emails/password_reset.txt')
                    html_content = html_template.render(**context)
                    text_content = text_template.render(**context)
                except Exception as e:
                    logger.warning(f"Failed to render password reset templates: {e}. Using fallback content.")
                    html_content = self._get_fallback_password_reset_html(context)
                    text_content = self._get_fallback_password_reset_text(context)
            else:
                html_content = self._get_fallback_password_reset_html(context)
                text_content = self._get_fallback_password_reset_text(context)

            # Send email
            success = await self.send_email(
                to_email=to_email,
                subject="Reset Your Password - Soccer Predictions Platform",
                html_content=html_content,
                text_content=text_content
            )

            if success:
                logger.info(f"Password reset email sent successfully to {to_email}")
            else:
                logger.warning(f"Failed to send password reset email to {to_email}")

            return success

        except Exception as e:
            logger.error(f"Failed to send password reset email to {to_email}: {str(e)}", exc_info=True)
            return False

    async def send_password_reset_confirmation_email(
        self,
        to_email: str,
        user_name: str
    ) -> bool:
        """
        Send password reset confirmation email

        Args:
            to_email: Recipient email address
            user_name: User's name

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Build login URL
            login_url = f"{settings.FRONTEND_URL}/login"

            # Prepare template context
            context = {
                'user_name': user_name,
                'login_url': login_url,
                'platform_name': 'Soccer Predictions Platform',
                'support_email': 'support@soccerpredictions.com',
                'year': '2025'
            }

            # Render templates
            if self.jinja_env:
                try:
                    html_template = self.jinja_env.get_template('emails/password_reset_confirmation.html')
                    text_template = self.jinja_env.get_template('emails/password_reset_confirmation.txt')
                    html_content = html_template.render(**context)
                    text_content = text_template.render(**context)
                except Exception as e:
                    logger.warning(f"Failed to render password reset confirmation templates: {e}. Using fallback content.")
                    html_content = self._get_fallback_password_reset_confirmation_html(context)
                    text_content = self._get_fallback_password_reset_confirmation_text(context)
            else:
                html_content = self._get_fallback_password_reset_confirmation_html(context)
                text_content = self._get_fallback_password_reset_confirmation_text(context)

            # Send email
            success = await self.send_email(
                to_email=to_email,
                subject="Password Reset Successful - Soccer Predictions Platform",
                html_content=html_content,
                text_content=text_content
            )

            if success:
                logger.info(f"Password reset confirmation email sent successfully to {to_email}")
            else:
                logger.warning(f"Failed to send password reset confirmation email to {to_email}")

            return success

        except Exception as e:
            logger.error(f"Failed to send password reset confirmation email to {to_email}: {str(e)}", exc_info=True)
            return False

    def _get_fallback_password_reset_html(self, context: Dict[str, Any]) -> str:
        """Get fallback HTML content for password reset email"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Reset Your Password</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px;">
                <h1 style="color: #2c3e50;">Reset Your Password</h1>
                <p>Hello {context['user_name']},</p>
                <p>We received a request to reset your password. Click the button below to reset it:</p>
                <p style="margin: 30px 0;">
                    <a href="{context['reset_url']}" style="background-color: #3498db; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Reset Password
                    </a>
                </p>
                <p>Or copy and paste this link: {context['reset_url']}</p>
                <p style="background-color: #fff3cd; padding: 15px; border-radius: 5px; color: #856404;">
                    <strong>Important:</strong> This link expires in 1 hour and can only be used once.
                </p>
                <p>If you didn't request this, please ignore this email.</p>
            </div>
        </body>
        </html>
        """

    def _get_fallback_password_reset_text(self, context: Dict[str, Any]) -> str:
        """Get fallback plain text content for password reset email"""
        return f"""
Reset Your Password

Hello {context['user_name']},

We received a request to reset your password. Click the link below to reset it:

{context['reset_url']}

IMPORTANT: This link expires in 1 hour and can only be used once.

If you didn't request this, please ignore this email.

---
{context['platform_name']}
        """

    def _get_fallback_password_reset_confirmation_html(self, context: Dict[str, Any]) -> str:
        """Get fallback HTML content for password reset confirmation email"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Password Reset Successful</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px;">
                <h1 style="color: #28a745;">Password Reset Successful!</h1>
                <p>Hello {context['user_name']},</p>
                <p>Your password has been successfully reset. You can now log in with your new password.</p>
                <p style="margin: 30px 0;">
                    <a href="{context['login_url']}" style="background-color: #28a745; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Log In Now
                    </a>
                </p>
                <p style="background-color: #fff3cd; padding: 15px; border-radius: 5px; color: #856404;">
                    <strong>Didn't reset your password?</strong> Contact support immediately.
                </p>
            </div>
        </body>
        </html>
        """

    def _get_fallback_password_reset_confirmation_text(self, context: Dict[str, Any]) -> str:
        """Get fallback plain text content for password reset confirmation email"""
        return f"""
Password Reset Successful!

Hello {context['user_name']},

Your password has been successfully reset. You can now log in with your new password.

Log in here: {context['login_url']}

DIDN'T RESET YOUR PASSWORD? Contact support immediately.

---
{context['platform_name']}
        """


# Create singleton instance
email_service = EmailService()

