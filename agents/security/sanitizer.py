"""
Input Sanitizer - Cleans and validates input text.
"""
import re
import html
import logging
import unicodedata
from typing import Optional

from agents.security.config import MAX_INPUT_LENGTH

logger = logging.getLogger("security.sanitizer")


class InputSanitizer:
    """
    Input Sanitizer - Cleans and validates input text.
    Removes dangerous content, normalizes Unicode, and ensures safe input.
    """
    
    def __init__(self):
        # Pattern to remove null bytes
        self.null_byte_pattern = re.compile(r'\x00')
        
        # Pattern to remove control characters (except newline and tab)
        self.control_char_pattern = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
        
        logger.info("InputSanitizer initialized")
    
    def sanitize(self, text: str, max_length: Optional[int] = None) -> str:
        """
        Sanitize input text.
        
        Args:
            text: Input text to sanitize
            max_length: Maximum allowed length (defaults to MAX_INPUT_LENGTH)
            
        Returns:
            Sanitized text
        """
        if not text:
            return text
        
        max_len = max_length or MAX_INPUT_LENGTH
        
        # Step 1: Remove null bytes
        text = self.null_byte_pattern.sub('', text)
        
        # Step 2: Remove control characters
        text = self.control_char_pattern.sub('', text)
        
        # Step 3: Normalize Unicode
        text = unicodedata.normalize('NFC', text)
        
        # Step 4: Strip leading/trailing whitespace
        text = text.strip()
        
        # Step 5: Limit length
        if len(text) > max_len:
            text = text[:max_len]
            logger.warning(f"Input truncated to {max_len} characters")
        
        return text
    
    def sanitize_html(self, text: str) -> str:
        """
        Sanitize HTML by escaping special characters.
        
        Args:
            text: Input text with potential HTML
            
        Returns:
            HTML-escaped text
        """
        if not text:
            return text
        
        # Escape HTML special characters
        return html.escape(text, quote=True)
    
    def sanitize_for_sql(self, text: str) -> str:
        """
        Sanitize text for SQL queries (additional safety beyond parameterized queries).
        
        Args:
            text: Input text
            
        Returns:
            Sanitized text
        """
        if not text:
            return text
        
        # Remove SQL comment markers
        text = text.replace('--', '')
        text = text.replace('/*', '')
        text = text.replace('*/', '')
        
        # Remove semicolons
        text = text.replace(';', '')
        
        return text
    
    def validate_encoding(self, text: str) -> bool:
        """
        Validate that text contains only valid UTF-8 characters.
        
        Args:
            text: Input text to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            text.encode('utf-8')
            return True
        except UnicodeEncodeError:
            return False
    
    def normalize_whitespace(self, text: str) -> str:
        """
        Normalize whitespace in text.
        
        Args:
            text: Input text
            
        Returns:
            Text with normalized whitespace
        """
        if not text:
            return text
        
        # Replace multiple spaces with single space
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
