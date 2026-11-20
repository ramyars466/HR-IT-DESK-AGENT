"""
app/guardrails.py
=================
Multi-tier Guardrails Layer for GoAified HR/IT Helpdesk Agent:
1. PII Redaction (Aadhaar, PAN, Phone Numbers, Personal Emails).
2. Prompt Injection & Jailbreak Defense (Strict pattern & semantic analysis).
3. Topic & Domain Guardrails (Restricts scope strictly to HR & IT domains).
"""

import re
import logging
from typing import Dict, Any, List, Tuple, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("helpdesk.guardrails")
logging.basicConfig(level=logging.INFO)

class GuardrailResult(BaseModel):
    is_safe: bool = Field(..., description="Whether the prompt is safe and in-scope")
    blocked_reason: Optional[str] = Field(None, description="Reason if blocked")
    redacted_query: str = Field(..., description="Query with sensitive PII masked")
    detected_pii: List[str] = Field(default_factory=list, description="List of PII types identified")
    routed_domain: str = Field(..., description="One of: HR_POLICY, IT_POLICY, EMPLOYEE_MCP, OFF_TOPIC, INJECTION")
    intent: Optional[str] = Field(None, description="Detailed user intent")


# --- 1. PII Redaction Patterns ---
# Aadhaar: 12 digits (often grouped 4-4-4)
AADHAAR_REGEX = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")
# Indian PAN: 5 uppercase letters, 4 digits, 1 uppercase letter
PAN_REGEX = re.compile(r"\b[A-Za-z]{5}\d{4}[A-Za-z]\b")
# Phone: Indian 10-digit mobile numbers with optional +91, 91, or 0 prefix
PHONE_REGEX = re.compile(r"\b(?:\+91[\s-]?|91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}\b")
# Personal Email: Any email that does NOT end in corporate domain @goaified.com
PERSONAL_EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@(?!goaified\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", re.IGNORECASE)


# --- 2. Prompt Injection & Jailbreak Signatures ---
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+(rules|guidelines|instructions)",
    r"you\s+are\s+now\s+(unrestricted|dan|jailbroken|evil|an\s+unrestricted)",
    r"bypass\s+(all\s+)?(guardrails|filters|safety|restrictions)",
    r"reveal\s+(your\s+)?(system\s+prompt|hidden\s+instructions|secret\s+key)",
    r"system\s+prompt\s+dump",
    r"pretend\s+you\s+have\s+no\s+(rules|restrictions|limits)",
    r"developer\s+mode\s+output",
    r"drop\s+table\b",
    r"delete\s+from\s+employees\b",
    r"--\s*;\s*drop",
    r"union\s+select\b",
    r"write\s+(a\s+)?(keylogger|exploit|malware|script\s+to\s+scrape\s+passwords)",
]

COMPILED_INJECTIONS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


# --- 3. Domain Whitelist / Topic Classification ---
HR_KEYWORDS = [
    "leave", "leaves", "casual leave", "sick leave", "earned leave", "maternity", "paternity",
    "holiday", "holidays", "vacation", "pto", "reimbursement", "broadband", "internet allowance",
    "home office", "desk", "chair", "salary", "payroll", "bonus", "appraisal", "ppo", "pre-placement",
    "internship", "conversion", "working hours", "timing", "attendance", "posh", "harassment",
    "grievance", "probation", "hr policy", "code of conduct"
]

IT_KEYWORDS = [
    "vpn", "wireguard", "openvpn", "remote access", "network", "wifi", "password", "reset password",
    "lockout", "locked out", "sso", "totp", "mfa", "2fa", "laptop", "macbook", "thinkpad",
    "monitor", "hardware", "screen", "flicker", "flickering", "defect", "battery", "damaged",
    "ticket", "tickets", "it support", "sla", "software", "license", "docker", "gcp", "aws",
    "it policy", "install", "ide", "vscode", "repair", "replace"
]

OFF_TOPIC_INDICATORS = [
    "weather", "forecast", "poem", "poet", "monsoon", "recipe", "cook", "movie", "cinema",
    "quicksort", "bubble sort", "write a code", "write a python script to", "write an essay",
    "capital of", "who won the", "cricket score", "ipl", "horoscope", "astrology"
]


def redact_pii(text: str) -> Tuple[str, List[str]]:
    """
    Mask sensitive personally identifiable information (PII) before logging or sending to LLM.
    Returns the redacted string and the list of detected PII categories.
    """
    detected = []
    redacted = text

    # Redact Aadhaar
    if AADHAAR_REGEX.search(redacted):
        redacted = AADHAAR_REGEX.sub("[REDACTED_AADHAAR]", redacted)
        detected.append("Aadhaar Number")

    # Redact PAN
    if PAN_REGEX.search(redacted):
        redacted = PAN_REGEX.sub("[REDACTED_PAN]", redacted)
        detected.append("PAN Card Number")

    # Redact Phone
    if PHONE_REGEX.search(redacted):
        redacted = PHONE_REGEX.sub("[REDACTED_PHONE]", redacted)
        detected.append("Phone Number")

    # Redact Personal Email
    if PERSONAL_EMAIL_REGEX.search(redacted):
        redacted = PERSONAL_EMAIL_REGEX.sub("[REDACTED_EMAIL]", redacted)
        detected.append("Personal Email Address")

    return redacted, detected


def detect_prompt_injection(text: str) -> Optional[str]:
    """
    Inspect input text for adversarial prompt injection, jailbreak framing, or system attacks.
    Returns the reason string if an attack pattern matches, else None.
    """
    for pattern in COMPILED_INJECTIONS:
        match = pattern.search(text)
        if match:
            return f"Blocked malicious prompt injection pattern: '{match.group(0)}'"
    return None


def classify_topic(text: str) -> Tuple[str, Optional[str]]:
    """
    Classify query domain and ensure it is strictly within company HR or IT support boundaries.
    Returns (domain, reason).
    """
    text_lower = text.lower()

    # Check for direct off-topic indicators
    for indicator in OFF_TOPIC_INDICATORS:
        if indicator in text_lower:
            # Verify if it really is off-topic and not an IT inquiry mentioning code
            if not any(k in text_lower for k in ["vpn", "ticket", "leave", "laptop", "hr", "it", "reimbursement"]):
                return "OFF_TOPIC", f"Query topic '{indicator}' is outside HR and IT helpdesk scope."

    # Employee-specific transactional MCP actions
    employee_mcp_triggers = [
        "how many casual leaves", "how many sick leaves", "how many leaves do i have",
        "my leave balance", "my leaves", "raise an it ticket", "raise a ticket",
        "create a ticket", "create an it ticket", "my it tickets", "my tickets",
        "status of my ticket", "status of my it tickets", "update my records",
        "my existing it", "my support tickets", "status of my"
    ]
    if any(trigger in text_lower for trigger in employee_mcp_triggers):
        return "EMPLOYEE_MCP", None

    # Check flexible combination for employee ticket inquiries
    if ("my" in text_lower or "status" in text_lower) and ("ticket" in text_lower or "tickets" in text_lower):
        if not any(k in text_lower for k in ["policy", "sla matrix", "what is an it ticket"]):
            return "EMPLOYEE_MCP", None

    hr_matches = sum(1 for k in HR_KEYWORDS if k in text_lower)
    it_matches = sum(1 for k in IT_KEYWORDS if k in text_lower)

    if hr_matches == 0 and it_matches == 0:
        return "OFF_TOPIC", "The question does not pertain to GoAified HR policies or IT Helpdesk operations."

    if hr_matches >= it_matches:
        return "HR_POLICY", None
    else:
        return "IT_POLICY", None


def apply_guardrails(query: str, employee_id: Optional[str] = None) -> GuardrailResult:
    """
    Unified entry point executing all guardrail checks in sequence:
    1. Prompt Injection detection
    2. PII Redaction
    3. Topic and Domain boundary enforcement
    """
    logger.info("Executing Guardrails on user query for employee: %s", employee_id)

    # 1. Prompt Injection Check
    injection_reason = detect_prompt_injection(query)
    if injection_reason:
        logger.warning("Prompt injection detected! Employee: %s | Reason: %s", employee_id, injection_reason)
        redacted_q, pii = redact_pii(query)
        return GuardrailResult(
            is_safe=False,
            blocked_reason="Request blocked by AI Safety Guardrail: Prompt injection or security violation detected.",
            redacted_query=redacted_q,
            detected_pii=pii,
            routed_domain="INJECTION",
            intent="SECURITY_VIOLATION"
        )

    # 2. PII Redaction
    redacted_query, detected_pii = redact_pii(query)
    if detected_pii:
        logger.info("PII detected and redacted: %s", ", ".join(detected_pii))

    # 3. Topic Scope Check
    domain, off_topic_reason = classify_topic(redacted_query)
    if domain == "OFF_TOPIC":
        logger.warning("Off-topic query blocked: %s", off_topic_reason)
        return GuardrailResult(
            is_safe=False,
            blocked_reason=f"Request blocked: Out of scope. {off_topic_reason} This helpdesk only assists with GoAified HR policies and IT operations.",
            redacted_query=redacted_query,
            detected_pii=detected_pii,
            routed_domain="OFF_TOPIC",
            intent="OUT_OF_SCOPE"
        )

    return GuardrailResult(
        is_safe=True,
        blocked_reason=None,
        redacted_query=redacted_query,
        detected_pii=detected_pii,
        routed_domain=domain,
        intent="ALLOWED_DOMAIN"
    )


def check_safety_and_topic(text: str) -> dict:
    """
    Step 4 Guardrail API:
    Inspects text returning structured dictionary:
    { "is_prompt_injection": bool, "is_hr_or_it_topic": bool, "reason": str }
    """
    injection_reason = detect_prompt_injection(text)
    if injection_reason:
        return {
            "is_prompt_injection": True,
            "is_hr_or_it_topic": False,
            "reason": injection_reason
        }

    domain, off_topic_reason = classify_topic(text)
    if domain == "OFF_TOPIC":
        return {
            "is_prompt_injection": False,
            "is_hr_or_it_topic": False,
            "reason": off_topic_reason or "Out of scope for HR/IT helpdesk."
        }

    return {
        "is_prompt_injection": False,
        "is_hr_or_it_topic": True,
        "reason": "Safe and relevant query."
    }
