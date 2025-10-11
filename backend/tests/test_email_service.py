"""
Tests for Email Service
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

from app.services.email_service import EmailService, email_service
from app.core.config import settings


class TestEmailService:
    """Test cases for EmailService"""
    
    @pytest.fixture
    def mock_email_service(self):
        """Create a mock email service for testing"""
        service = EmailService()
        service.enabled = True
        service.provider = "smtp"
        return service
    
    @pytest.mark.asyncio
    async def test_send_email_disabled(self, mock_email_service):
        """Test that email sending is skipped when disabled"""
        mock_email_service.enabled = False
        
        result = await mock_email_service.send_email(
            to_email="test@example.com",
            subject="Test Subject",
            html_content="<p>Test</p>",
            text_content="Test"
        )
        
        assert result is True  # Should return True even when disabled
    
    @pytest.mark.asyncio
    @patch('app.services.email_service.aiosmtplib.send')
    async def test_send_email_via_smtp_success(self, mock_smtp_send, mock_email_service):
        """Test successful email sending via SMTP"""
        mock_smtp_send.return_value = AsyncMock()
        
        # Configure settings
        settings.SMTP_HOST = "smtp.example.com"
        settings.SMTP_PORT = 587
        settings.SMTP_USER = "user@example.com"
        settings.SMTP_PASSWORD = "password"
        settings.EMAILS_FROM_EMAIL = "noreply@example.com"
        settings.EMAILS_FROM_NAME = "Test Platform"
        
        result = await mock_email_service.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            html_content="<p>Test HTML</p>",
            text_content="Test Text"
        )
        
        assert result is True
        mock_smtp_send.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.services.email_service.aiosmtplib.send')
    async def test_send_email_via_smtp_failure(self, mock_smtp_send, mock_email_service):
        """Test email sending failure via SMTP"""
        mock_smtp_send.side_effect = Exception("SMTP connection failed")
        
        settings.SMTP_HOST = "smtp.example.com"
        settings.SMTP_PORT = 587
        settings.SMTP_USER = "user@example.com"
        settings.SMTP_PASSWORD = "password"
        settings.EMAILS_FROM_EMAIL = "noreply@example.com"
        
        result = await mock_email_service.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            html_content="<p>Test HTML</p>"
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_email_no_sender_configured(self, mock_email_service):
        """Test email sending fails when no sender email is configured"""
        settings.EMAILS_FROM_EMAIL = None
        
        result = await mock_email_service.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            html_content="<p>Test HTML</p>"
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_email_unknown_provider(self, mock_email_service):
        """Test email sending fails with unknown provider"""
        mock_email_service.provider = "unknown_provider"
        
        result = await mock_email_service.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            html_content="<p>Test HTML</p>"
        )
        
        assert result is False
    
    def test_render_template(self, mock_email_service):
        """Test template rendering"""
        # Create a simple template for testing
        from jinja2 import Environment, DictLoader
        
        mock_email_service.jinja_env = Environment(
            loader=DictLoader({
                'test.html': '<p>Hello {{ name }}!</p>'
            })
        )
        
        result = mock_email_service.render_template('test.html', {'name': 'John'})
        assert result == '<p>Hello John!</p>'
    
    def test_render_template_no_env(self, mock_email_service):
        """Test template rendering fails when environment not initialized"""
        mock_email_service.jinja_env = None
        
        with pytest.raises(ValueError, match="Template environment not initialized"):
            mock_email_service.render_template('test.html', {})
    
    @pytest.mark.asyncio
    @patch('app.services.email_service.aiosmtplib.send')
    async def test_send_welcome_email_success(self, mock_smtp_send, mock_email_service):
        """Test sending welcome email"""
        mock_smtp_send.return_value = AsyncMock()
        
        settings.SMTP_HOST = "smtp.example.com"
        settings.SMTP_PORT = 587
        settings.SMTP_USER = "user@example.com"
        settings.SMTP_PASSWORD = "password"
        settings.EMAILS_FROM_EMAIL = "noreply@example.com"
        settings.FRONTEND_URL = "http://localhost:3000"
        
        result = await mock_email_service.send_welcome_email(
            to_email="newuser@example.com",
            user_name="John Doe",
            user_id="123e4567-e89b-12d3-a456-426614174000"
        )
        
        assert result is True
        mock_smtp_send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_welcome_email_with_fallback_content(self, mock_email_service):
        """Test welcome email uses fallback content when templates not found"""
        mock_email_service.jinja_env = None
        mock_email_service.enabled = False  # Disable to avoid actual sending
        
        result = await mock_email_service.send_welcome_email(
            to_email="newuser@example.com",
            user_name="John Doe",
            user_id="123e4567-e89b-12d3-a456-426614174000"
        )
        
        assert result is True  # Should succeed with fallback content
    
    def test_fallback_welcome_html(self, mock_email_service):
        """Test fallback HTML content generation"""
        context = {
            "user_name": "John Doe",
            "platform_name": "Test Platform",
            "frontend_url": "http://localhost:3000",
            "dashboard_url": "http://localhost:3000/dashboard",
            "support_email": "support@example.com",
            "year": 2025
        }
        
        html = mock_email_service._get_fallback_welcome_html(context)
        
        assert "John Doe" in html
        assert "Test Platform" in html
        assert "http://localhost:3000/dashboard" in html
        assert "support@example.com" in html
    
    def test_fallback_welcome_text(self, mock_email_service):
        """Test fallback plain text content generation"""
        context = {
            "user_name": "John Doe",
            "platform_name": "Test Platform",
            "frontend_url": "http://localhost:3000",
            "dashboard_url": "http://localhost:3000/dashboard",
            "support_email": "support@example.com",
            "year": 2025
        }
        
        text = mock_email_service._get_fallback_welcome_text(context)
        
        assert "John Doe" in text
        assert "Test Platform" in text
        assert "http://localhost:3000/dashboard" in text
        assert "support@example.com" in text
    
    @pytest.mark.asyncio
    async def test_send_via_sendgrid_not_implemented(self, mock_email_service):
        """Test SendGrid provider returns False (not implemented)"""
        mock_email_service.provider = "sendgrid"
        
        result = await mock_email_service.send_email(
            to_email="test@example.com",
            subject="Test",
            html_content="<p>Test</p>"
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_via_ses_not_implemented(self, mock_email_service):
        """Test AWS SES provider returns False (not implemented)"""
        mock_email_service.provider = "ses"
        
        result = await mock_email_service.send_email(
            to_email="test@example.com",
            subject="Test",
            html_content="<p>Test</p>"
        )
        
        assert result is False
    
    def test_email_service_singleton(self):
        """Test that email_service is a singleton instance"""
        assert isinstance(email_service, EmailService)
    
    @pytest.mark.asyncio
    @patch('app.services.email_service.aiosmtplib.send')
    async def test_send_email_with_custom_sender(self, mock_smtp_send, mock_email_service):
        """Test sending email with custom sender"""
        mock_smtp_send.return_value = AsyncMock()
        
        settings.SMTP_HOST = "smtp.example.com"
        settings.SMTP_PORT = 587
        settings.SMTP_USER = "user@example.com"
        settings.SMTP_PASSWORD = "password"
        settings.EMAILS_FROM_EMAIL = "default@example.com"
        
        result = await mock_email_service.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            html_content="<p>Test HTML</p>",
            from_email="custom@example.com",
            from_name="Custom Sender"
        )
        
        assert result is True
        mock_smtp_send.assert_called_once()

