"""
Security types and data structures.
Separated to avoid circular imports.
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class SecurityResult:
    """Security check result."""
    is_safe: bool
    threat_type: Optional[str] = None
    threat_level: Optional[str] = None
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    sanitized_text: Optional[str] = None
