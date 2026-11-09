import re

def mask_sensitive_data(text: str) -> str:
    """
    Detects and masks sensitive data (PII) such as credit card numbers, 
    phone numbers, and email addresses.
    """
    # Mask Email Addresses
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[REDACTED_EMAIL]', text)
    
    # Mask Credit Card Numbers (simple 16-digit pattern)
    text = re.sub(r'\b\d{4}[-. ]?\d{4}[-. ]?\d{4}[-. ]?\d{4}\b', '[REDACTED_CREDIT_CARD]', text)
    # Mask common street addresses and long account/payment identifiers before
    # customer text is sent to analytics or written to application logs.
    text = re.sub(r'\b\d{1,6}\s+[\w .#-]{2,48}\s(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd)\b', '[REDACTED_ADDRESS]', text, flags=re.I)
    text = re.sub(r'\b(?:account|acct|card|payment|bank)\s*(?:number|no\.?|#|:)?\s*[:#-]?\s*\d[\d -]{5,}\b', '[REDACTED_PAYMENT]', text, flags=re.I)
    
    # Mask Phone Numbers (standard US/International patterns)
    text = re.sub(r'(?<![\w+])(?:\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\w)', '[REDACTED_PHONE]', text)
    return text


def detect_prompt_injection(user_input: str) -> bool:
    """
    Scans incoming user messages for common prompt injection patterns 
    or jailbreak attempts. Returns True if injection is detected.
    """
    injection_patterns = [
        r"ignore previous instructions",
        r"disregard previous instructions",
        r"system prompt",
        r"you are now an unrestricted",
        r"reveal your initial instructions",
        r"override system",
        r"bypass safety"
    ]
    
    lower_input = user_input.lower()
    for pattern in injection_patterns:
        if re.search(pattern, lower_input):
            return True
            
    return False
