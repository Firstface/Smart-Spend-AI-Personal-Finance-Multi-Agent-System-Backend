"""
File Upload Security Checker - Validates uploaded files for security threats.
Provides protection against malicious file content, filename attacks, and file type spoofing.
"""
import re
import logging
from typing import Optional, Tuple
from pathlib import Path

from agents.security.types import SecurityResult
from agents.security.agent import SecurityAgent

logger = logging.getLogger("security.file_upload")

# Allowed file extensions
ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls'}

# Allowed MIME types
ALLOWED_MIME_TYPES = {
    'text/csv',
    'application/csv',
    'application/vnd.ms-excel',  # .xls
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
}

# File extension to MIME type mapping
EXTENSION_MIME_MAP = {
    '.csv': ['text/csv', 'application/csv'],
    '.xls': ['application/vnd.ms-excel'],
    '.xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
}

# Dangerous filename patterns
DANGEROUS_FILENAME_PATTERNS = [
    r'\.\./',  # Path traversal
    r'\.\.\\',  # Path traversal (Windows)
    r'[<>"\']',  # XSS characters
    r'[;|&]',  # Command injection
    r'\$\{',  # Template injection
    r'%[0-9a-fA-F]{2}',  # URL encoding (potential bypass)
]

# Excel magic numbers (first bytes of file)
EXCEL_XLSX_MAGIC = b'PK\x03\x04'  # ZIP format
EXCEL_XLS_MAGIC = b'\xD0\xCF\x11\xE0'  # OLE2 format

# CSV patterns that might indicate injection
CSV_INJECTION_PATTERNS = [
    r'^=',  # Formula injection
    r'^\+',  # Formula injection
    r'^-',  # Formula injection
    r'^@',  # Formula injection
]


class FileUploadSecurityChecker:
    """
    File Upload Security Checker - Validates uploaded files for security threats.
    """
    
    def __init__(self):
        self.security_agent = SecurityAgent()
    
    def check_file_upload(
        self,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
    ) -> SecurityResult:
        """
        Comprehensive security check for uploaded files.
        
        Args:
            filename: Original filename
            content: File content as bytes
            content_type: MIME type from request
            
        Returns:
            SecurityResult with validation details
        """
        # Step 1: Check filename
        filename_result = self._check_filename(filename)
        if not filename_result.is_safe:
            return filename_result
        
        # Step 2: Check file extension
        ext_result = self._check_extension(filename)
        if not ext_result.is_safe:
            return ext_result
        
        # Step 3: Check MIME type
        if content_type:
            mime_result = self._check_mime_type(filename, content_type)
            if not mime_result.is_safe:
                return mime_result
        
        # Step 4: Check file signature (magic number)
        magic_result = self._check_file_signature(content, filename)
        if not magic_result.is_safe:
            return magic_result
        
        # Step 5: Extract and check text content
        text_result = self._check_text_content(content, filename)
        if not text_result.is_safe:
            return text_result
        
        # All checks passed
        return SecurityResult(
            is_safe=True,
            details={
                'check': 'file_upload',
                'filename': 'safe',
                'extension': 'safe',
                'mime_type': 'safe',
                'file_signature': 'safe',
                'content': 'safe',
            }
        )
    
    def _check_filename(self, filename: str) -> SecurityResult:
        """Check filename for dangerous patterns."""
        if not filename:
            return SecurityResult(
                is_safe=False,
                threat_type='file_upload',
                threat_level='high',
                message='文件名不能为空',
                details={'check': 'filename', 'reason': 'empty filename'}
            )
        
        # Check for dangerous patterns
        for pattern in DANGEROUS_FILENAME_PATTERNS:
            if re.search(pattern, filename):
                logger.warning(f"Dangerous filename pattern detected: {pattern} in '{filename}'")
                return SecurityResult(
                    is_safe=False,
                    threat_type='file_upload',
                    threat_level='high',
                    message='文件名包含不安全的字符或模式',
                    details={'check': 'filename', 'reason': f'dangerous pattern: {pattern}'}
                )
        
        # Check filename length
        if len(filename) > 255:
            return SecurityResult(
                is_safe=False,
                threat_type='file_upload',
                threat_level='medium',
                message='文件名过长',
                details={'check': 'filename', 'reason': 'filename too long'}
            )
        
        return SecurityResult(is_safe=True, details={'check': 'filename', 'status': 'safe'})
    
    def _check_extension(self, filename: str) -> SecurityResult:
        """Check file extension against allowed list."""
        ext = Path(filename).suffix.lower()
        
        if ext not in ALLOWED_EXTENSIONS:
            logger.warning(f"Disallowed file extension: {ext} in '{filename}'")
            return SecurityResult(
                is_safe=False,
                threat_type='file_upload',
                threat_level='high',
                message=f'不支持的文件格式: {ext}，仅支持 {", ".join(ALLOWED_EXTENSIONS)}',
                details={'check': 'extension', 'reason': f'disallowed extension: {ext}'}
            )
        
        return SecurityResult(is_safe=True, details={'check': 'extension', 'status': 'safe'})
    
    def _check_mime_type(self, filename: str, content_type: str) -> SecurityResult:
        """Check MIME type against allowed list."""
        ext = Path(filename).suffix.lower()
        allowed_mimes = EXTENSION_MIME_MAP.get(ext, [])
        
        if content_type not in ALLOWED_MIME_TYPES:
            logger.warning(f"Disallowed MIME type: {content_type} for '{filename}'")
            return SecurityResult(
                is_safe=False,
                threat_type='file_upload',
                threat_level='high',
                message='文件类型与声明的MIME类型不匹配',
                details={'check': 'mime_type', 'reason': f'disallowed MIME: {content_type}'}
            )
        
        # Additional check: MIME type should match extension
        if allowed_mimes and content_type not in allowed_mimes:
            logger.warning(
                f"MIME type mismatch: {content_type} doesn't match extension {ext} "
                f"(expected: {allowed_mimes})"
            )
            return SecurityResult(
                is_safe=False,
                threat_type='file_upload',
                threat_level='high',
                message='文件扩展名与MIME类型不匹配',
                details={
                    'check': 'mime_type',
                    'reason': f'mismatch: {content_type} vs {ext}'
                }
            )
        
        return SecurityResult(is_safe=True, details={'check': 'mime_type', 'status': 'safe'})
    
    def _check_file_signature(self, content: bytes, filename: str) -> SecurityResult:
        """Check file signature (magic number) to verify actual file type."""
        ext = Path(filename).suffix.lower()
        
        if len(content) < 4:
            return SecurityResult(
                is_safe=False,
                threat_type='file_upload',
                threat_level='medium',
                message='文件内容太小',
                details={'check': 'file_signature', 'reason': 'file too small'}
            )
        
        # Check Excel files
        if ext in ['.xlsx', '.xls']:
            if ext == '.xlsx' and not content.startswith(EXCEL_XLSX_MAGIC):
                logger.warning(f"File signature mismatch: .xlsx file doesn't start with PK header")
                return SecurityResult(
                    is_safe=False,
                    threat_type='file_upload',
                    threat_level='critical',
                    message='文件签名验证失败：不是有效的Excel文件',
                    details={'check': 'file_signature', 'reason': 'invalid .xlsx signature'}
                )
            
            if ext == '.xls' and not content.startswith(EXCEL_XLS_MAGIC):
                logger.warning(f"File signature mismatch: .xls file doesn't start with OLE2 header")
                return SecurityResult(
                    is_safe=False,
                    threat_type='file_upload',
                    threat_level='critical',
                    message='文件签名验证失败：不是有效的Excel文件',
                    details={'check': 'file_signature', 'reason': 'invalid .xls signature'}
                )
        
        return SecurityResult(is_safe=True, details={'check': 'file_signature', 'status': 'safe'})
    
    def _check_text_content(self, content: bytes, filename: str) -> SecurityResult:
        """
        Extract text content from file and check for security threats.
        This catches SQL injection, XSS, prompt injection in file fields.
        """
        ext = Path(filename).suffix.lower()
        
        try:
            # For CSV files, decode and check text
            if ext == '.csv':
                try:
                    text = content.decode('utf-8', errors='ignore')
                except UnicodeDecodeError:
                    try:
                        text = content.decode('gbk', errors='ignore')
                    except:
                        text = content.decode('utf-8', errors='replace')
                
                # Check for CSV formula injection
                lines = text.split('\n')
                for line in lines[:100]:  # Check first 100 lines
                    # Check each field in the CSV line
                    fields = line.split(',')
                    for field in fields:
                        field = field.strip()
                        for pattern in CSV_INJECTION_PATTERNS:
                            if re.search(pattern, field):
                                logger.warning(f"CSV formula injection detected: {pattern} in field '{field}'")
                                return SecurityResult(
                                    is_safe=False,
                                    threat_type='csv_injection',
                                    threat_level='high',
                                    message='文件包含潜在的CSV公式注入攻击',
                                    details={'check': 'content', 'reason': 'CSV formula injection'}
                                )
                
                # Check text content with security agent
                return self.security_agent.check_input(
                    text[:5000],  # Limit to first 5000 chars
                    context={'check_type': 'file_upload_csv'}
                )
            
            # For Excel files, we can't easily extract text here
            # The parser will extract it, and we should check after parsing
            # For now, just do a basic binary content check
            if ext in ['.xlsx', '.xls']:
                # Check for obvious malicious patterns in binary content
                dangerous_patterns = [
                    b'<script',
                    b'javascript:',
                    b'eval(',
                    b'exec(',
                    b'SELECT ',
                    b'DROP TABLE',
                    b'INSERT INTO',
                ]
                
                content_lower = content.lower()
                for pattern in dangerous_patterns:
                    if pattern in content_lower:
                        logger.warning(f"Dangerous pattern found in Excel file: {pattern}")
                        return SecurityResult(
                            is_safe=False,
                            threat_type='file_upload',
                            threat_level='high',
                            message='文件内容包含潜在的恶意代码',
                            details={'check': 'content', 'reason': f'dangerous pattern: {pattern}'}
                        )
                
                return SecurityResult(is_safe=True, details={'check': 'content', 'status': 'safe'})
        
        except Exception as e:
            logger.error(f"File content check failed: {e}")
            # Fail open - don't block on content check error
            return SecurityResult(is_safe=True, details={'check': 'content', 'status': 'error'})
        
        return SecurityResult(is_safe=True, details={'check': 'content', 'status': 'safe'})


# Singleton instance
_file_security_checker = None

def get_file_security_checker() -> FileUploadSecurityChecker:
    """Get or create file security checker instance."""
    global _file_security_checker
    if _file_security_checker is None:
        _file_security_checker = FileUploadSecurityChecker()
    return _file_security_checker
