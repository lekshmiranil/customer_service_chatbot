"""Probe, not a test: prints what mask_sensitive_data does to sample customer messages. No model, no quota."""
from src.pipeline.security import mask_sensitive_data

SAMPLES = [
    "my card is 4111 1111 1111 1111",
    "call me on 9876543210",
    "call me on +91 98765 43210",
    "call me on +919876543210",
    "where is my order ORD-12345",
    "where is my order ORD-1234567890",
    "mail me at anu.menon@example.com",
    "delivery was promised on 12/11/2026",
]

for text in SAMPLES:
    print(ascii(text), "->", ascii(mask_sensitive_data(text)))