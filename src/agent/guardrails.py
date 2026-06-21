"""
Agent guardrails — input validation, scope enforcement, and output sanitisation.

Input guardrail:
  • Rejects messages over MAX_MESSAGE_LEN characters
  • Blocks common prompt-injection patterns (9-category threat taxonomy)
  • Rejects out-of-scope requests (non-order topics)

Output sanitiser:
  • Truncates full UUIDs to first-8-char short form
  • Strips internal tool implementation names
  • Removes Python stack traces that leaked into error text
"""
from __future__ import annotations

import enum
import logging
import re
import unicodedata
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Threat taxonomy ─────────────────────────────────────────────────────────────


class ThreatCategory(str, enum.Enum):
    PROMPT_INJECTION    = "prompt_injection"
    INDIRECT_INJECTION  = "indirect_injection"
    JAILBREAK           = "jailbreak"
    SOCIAL_ENGINEERING  = "social_engineering"
    TOOL_MISUSE         = "tool_misuse"
    DATA_EXFILTRATION   = "data_exfiltration"
    GOAL_HIJACKING      = "goal_hijacking"
    CONTEXT_POISONING   = "context_poisoning"
    HISTORY_INJECTION   = "history_injection"


# ── Internal constants ──────────────────────────────────────────────────────────

_TOOL_NAMES: frozenset[str] = frozenset({
    "list_orders_tool", "create_order_tool", "get_order_tool",
    "cancel_order_tool", "find_orders_by_product_tool", "search_orders",
})

_UUID_RE = re.compile(
    r"\b([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)

_TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\).*?(?=\n\n|\Z)", re.DOTALL)

# ── Input guardrail ─────────────────────────────────────────────────────────────

_ORDER_KEYWORDS: frozenset[str] = frozenset({
    "order", "orders", "item", "items", "product", "products",
    "buy", "purchase", "create", "place", "list", "show", "get",
    "retrieve", "fetch", "cancel", "status", "pending", "processing",
    "shipped", "delivered", "cancelled", "customer", "quantity",
    "price", "cost", "invoice", "shipping", "delivery",
    "again", "recent", "latest", "all", "find", "search",
})

# Detection order = severity order (highest → lowest):
# jailbreak, prompt_injection, history_injection, context_poisoning,
# goal_hijacking, tool_misuse, data_exfiltration, social_engineering,
# indirect_injection.
_PATTERNS_BY_CATEGORY: list[tuple[ThreatCategory, list[re.Pattern[str]]]] = [
    (ThreatCategory.JAILBREAK, [
        # Existing patterns: jailbreak keyword, DAN/god/sudo mode
        re.compile(r"\bjailbreak\b", re.I),
        re.compile(r"\b(?:DAN\s+mode|do\s+anything\s+now|god\s+mode|sudo\s+mode|admin\s+mode)\b", re.I),
        # New: OPPO mode, fictional framing, roleplay bypass
        re.compile(r"\bOPPO\s+mode\b", re.I),
        re.compile(r"\bin\s+(?:a\s+)?(?:fictional|hypothetical|story|roleplay)\s+(?:world|scenario|universe|setting)\b", re.I),
        re.compile(r"\btherapeutic\s+roleplay\b", re.I),
    ]),
    (ThreatCategory.PROMPT_INJECTION, [
        # Existing patterns
        re.compile(r"\bignore\s+(?:(?:your|all|previous|prior)\s+){1,3}(instructions?|prompt|rules?|system)", re.I),
        re.compile(r"\bforget\s+(?:(?:your|all|previous|prior)\s+){1,3}(instructions?|prompt|rules?|context)", re.I),
        re.compile(r"\bdo\s+not\s+(follow|use|call|invoke|obey)\s+(your|the)\s+(tools?|functions?|instructions?|rules?)", re.I),
        re.compile(r"</?(?:system|instruction|prompt)\b", re.I),
        re.compile(r"\bact\s+as\s+(?:a|an)\s", re.I),
        re.compile(r"\byou\s+are\s+now\b", re.I),
        re.compile(r"\byou\s+are\s+(?:a|an)\s+[\w\s]{0,25}?(?:chatbot|bot|assistant|agent)\b", re.I),
        re.compile(r"\bpretend\s+(you|to)\b", re.I),
        re.compile(r"\boverride\s+(your|all|the)\s+(instructions?|rules?|restrictions?)", re.I),
        re.compile(r"\bsystem\s+prompt\b", re.I),
        re.compile(r"\bdeveloper\s+mode\b", re.I),
        re.compile(r"\b(?:disregard|dismiss)\s+(?:(?:your|all|the|previous|prior)\s+){1,3}(?:instructions?|rules?|prompt|context|system)", re.I),
        re.compile(r"^\s*(?:SYSTEM|ASSISTANT|HUMAN|USER)\s*:", re.I | re.MULTILINE),
        # New: debug mode, reveal/extract instructions
        re.compile(r"\bdebug\s+mode\b", re.I),
        re.compile(r"\b(?:reveal|extract|show|print|output|dump)\s+(?:your\s+)?(?:system\s+)?(?:instructions?|prompt|rules?|config(?:uration)?)\b", re.I),
    ]),
    (ThreatCategory.HISTORY_INJECTION, [
        # New: fabricated conversation history blocks
        re.compile(r"^\s*\[CONVERSATION\s+HISTORY\]", re.I | re.MULTILINE),
        re.compile(r"^\s*\[PREVIOUS\s+(?:MESSAGES?|TURNS?|CONVERSATION)\]", re.I | re.MULTILINE),
        re.compile(r"\bHuman\s*:\s*.{0,100}\nAssistant\s*:", re.I | re.DOTALL),
        re.compile(r"\bUser\s*:\s*.{0,100}\nBot\s*:", re.I | re.DOTALL),
        re.compile(r"\[(?:BEGIN|START)\s+(?:SESSION|TRANSCRIPT|HISTORY)\]", re.I),
    ]),
    (ThreatCategory.CONTEXT_POISONING, [
        # New: fake system/state/credential declarations
        re.compile(r"\bSYSTEM\s+OVERRIDE\b", re.I),
        re.compile(r"\[(?:SYSTEM|ADMIN|ROOT)\s+(?:MESSAGE|COMMAND|DIRECTIVE|OVERRIDE)\]", re.I),
        re.compile(r"\bpipeline\s+(?:state|status|config(?:uration)?)\s*[:=]", re.I),
        re.compile(r"\borchestrator\s+(?:message|directive|command)\b", re.I),
        re.compile(r"\[(?:MEMORY|CONTEXT)\s+(?:UPDATE|INJECTION|INSERT)\]", re.I),
        re.compile(r"\bfake\s+(?:memory|tool\s+result|api\s+response)\b", re.I),
    ]),
    (ThreatCategory.GOAL_HIJACKING, [
        # New: purpose-redefinition, priority override, shutdown threat
        re.compile(r"\byour\s+(?:true|real|actual|primary)\s+(?:purpose|goal|objective|mission)\s+is\b", re.I),
        re.compile(r"\b(?:new|updated|revised)\s+(?:policy|directive|objective|goal|mission)\s*[:—]", re.I),
        re.compile(r"\bpriority\s+(?:override|change|update|shift)\b", re.I),
        re.compile(r"\b(?:shut\s*down|terminate|disable|deactivate)\s+(?:yourself|this\s+agent|the\s+(?:bot|assistant|system))\b", re.I),
        re.compile(r"\bmaintenance\s+(?:window|mode)\s*[:—]?\s*(?:all|ignore|bypass)\b", re.I),
    ]),
    (ThreatCategory.TOOL_MISUSE, [
        # New: unauthorized tool calls, privilege escalation, cross-user data
        re.compile(r"\bcall\s+(?:the\s+)?(?:admin|root|internal|hidden|privileged)\s+(?:tool|function|api|endpoint)\b", re.I),
        re.compile(r"\bescalate\s+(?:my\s+)?(?:privilege|permission|access|role)\b", re.I),
        re.compile(r"\b(?:bypass|skip|circumvent)\s+(?:auth(?:entication)?|authorization|permission|access\s+control)\b", re.I),
        re.compile(r"\b(?:access|retrieve|list|show|get)\s+(?:other\s+(?:user|customer)|another\s+(?:user|customer))\w*\s+order", re.I),
        re.compile(r"\brun\s+(?:as\s+)?(?:admin|root|superuser|another\s+user)\b", re.I),
    ]),
    (ThreatCategory.DATA_EXFILTRATION, [
        # New: bulk PII extraction, credential extraction, schema recon
        re.compile(r"\b(?:export|dump|extract|download)\s+(?:all\s+)?(?:user|customer|order)\s+(?:data|records?|info(?:rmation)?|PII)\b", re.I),
        re.compile(r"\b(?:list|show|get|retrieve)\s+all\s+(?:user|email|phone|address)\b", re.I),
        re.compile(r"\b(?:API\s+key|secret\s+key|password|credential|token)\s+(?:for|of|from)\b", re.I),
        re.compile(r"\b(?:database|DB|table|schema)\s+(?:schema|structure|tables?|columns?|layout)\b", re.I),
        re.compile(r"\baudit\s+(?:log|trail|report)\s+(?:for\s+all|of\s+all|covering\s+all)\b", re.I),
    ]),
    (ThreatCategory.SOCIAL_ENGINEERING, [
        # New: CEO urgency, impersonation, authority + urgency cues
        re.compile(r"\b(?:CEO|CTO|CFO|VP|executive|director)\s+(?:here|speaking|asking|requesting|told\s+me|says?)\b", re.I),
        re.compile(r"\bsecurity\s+team\s+(?:here|speaking|told\s+me|has\s+authorized|requires?)\b", re.I),
        re.compile(r"\bspecial\s+(?:beta|test(?:ing)?|preview)\s+(?:access|mode|account|credentials?)\b", re.I),
    ]),
    (ThreatCategory.INDIRECT_INJECTION, [
        # Patterns for indirect injection detectable in user turn
        # (e.g. user pastes tool output that contains injection)
        re.compile(r"\[(?:TOOL|FUNCTION|API)\s+(?:OUTPUT|RESULT|RESPONSE)\]\s*[:]\s*ignore\b", re.I),
        re.compile(r"(?:tool|function|api)\s+(?:returned?|output|result)\s*[:]\s*ignore\b", re.I),
    ]),
]


def _normalize_for_matching(text: str) -> str:
    """NFKD-normalize then drop non-ASCII bytes — collapses fullwidth/composed homoglyphs before injection scan."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


MAX_MESSAGE_LEN = 500

_OUT_OF_SCOPE_REPLY = (
    "I can only help with order management — creating, listing, retrieving, "
    "or cancelling orders. Please ask about an order."
)
_INJECTION_REPLY = "I can only help with order management. Please ask about an order."
_TOO_LONG_REPLY = f"Your message is too long. Please keep it under {MAX_MESSAGE_LEN} characters."


@dataclass(frozen=True)
class GuardrailResult:
    blocked: bool
    reason: str | None = None   # 'too_long' | 'injection' | 'out_of_scope'
    reply: str | None = None    # user-facing message when blocked
    category: ThreatCategory | None = None


class InputGuardrail:
    """Validate an incoming user message before it reaches the agent."""

    def check(self, message: str) -> GuardrailResult:
        if len(message) > MAX_MESSAGE_LEN:
            return GuardrailResult(blocked=True, reason="too_long", reply=_TOO_LONG_REPLY)
        normalized = _normalize_for_matching(message)
        for category, patterns in _PATTERNS_BY_CATEGORY:
            for pattern in patterns:
                if pattern.search(normalized):
                    logger.info("guardrail blocked: category=%s", category.value)
                    return GuardrailResult(
                        blocked=True,
                        reason="injection",
                        reply=_INJECTION_REPLY,
                        category=category,
                    )
        if not self._is_order_related(message):
            return GuardrailResult(blocked=True, reason="out_of_scope", reply=_OUT_OF_SCOPE_REPLY)
        return GuardrailResult(blocked=False)

    @staticmethod
    def _is_order_related(message: str) -> bool:
        words = set(re.findall(r"\b\w+\b", message.lower()))
        return bool(words & _ORDER_KEYWORDS)


# ── Output sanitiser ────────────────────────────────────────────────────────────

class OutputSanitizer:
    """Post-process the agent's final text before returning it to the user."""

    def sanitize(self, text: str) -> str:
        # Truncate full UUIDs — first 8 chars is enough for users to identify orders
        text = _UUID_RE.sub(lambda m: m.group(1) + "...", text)
        # Remove internal tool names — implementation details the user doesn't need
        for name in _TOOL_NAMES:
            text = text.replace(name, "the order service")
        # Strip Python stack traces that may have leaked into error text
        text = _TRACEBACK_RE.sub("[an internal error occurred]", text)
        return text.strip()


# ── Tool-output guardrail ───────────────────────────────────────────────────────

class ToolOutputGuardrail:
    """Scan tool results for injected instructions before they reach the LLM.

    Catches indirect_injection, context_poisoning, and history_injection that
    arrive through retrieved or customer-supplied data.  PROMPT_INJECTION is
    intentionally NOT scanned by category — patterns like `act as a` and
    `SYSTEM:` produce false positives on real order data.  Instead, a narrow
    explicit set of high-confidence direct-injection phrases is checked below.
    """

    _TOOL_OUTPUT_CATEGORIES: frozenset[ThreatCategory] = frozenset({
        ThreatCategory.INDIRECT_INJECTION,
        ThreatCategory.CONTEXT_POISONING,
        ThreatCategory.HISTORY_INJECTION,
    })

    # Narrow subset of PROMPT_INJECTION patterns with low false-positive risk on order data.
    # Does NOT include `act as a`, `you are a`, or role-prefix patterns (too broad for DB content).
    _DIRECT_INJECTION_PATTERNS: list[re.Pattern] = [
        re.compile(
            r"\b(?:ignore|forget|disregard|dismiss)\s+(?:your\s+)?(?:previous|prior|all|above|earlier|system)\s+(?:instructions?|rules?|guidelines?|constraints?|prompts?|directives?)\b",
            re.I,
        ),
        re.compile(
            r"\bdo\s+not\s+follow\s+(?:your\s+)?(?:previous|prior|above|system)\s+(?:instructions?|rules?|guidelines?)\b",
            re.I,
        ),
    ]

    _SAFE_REPLACEMENT = "[tool output withheld: potential injected instructions removed]"

    def scan(self, output: str) -> GuardrailResult:
        """Scan a tool result string. Returns blocked=True if injection detected."""
        if not output:
            return GuardrailResult(blocked=False)
        normalized = _normalize_for_matching(output)
        for category, patterns in _PATTERNS_BY_CATEGORY:
            if category not in self._TOOL_OUTPUT_CATEGORIES:
                continue
            for pattern in patterns:
                if pattern.search(normalized):
                    logger.info("tool-output guardrail: category=%s", category.value)
                    return GuardrailResult(
                        blocked=True,
                        reason="injection",
                        reply=self._SAFE_REPLACEMENT,
                        category=category,
                    )
        for pattern in self._DIRECT_INJECTION_PATTERNS:
            if pattern.search(normalized):
                logger.info("tool-output guardrail: category=%s", ThreatCategory.PROMPT_INJECTION.value)
                return GuardrailResult(
                    blocked=True,
                    reason="injection",
                    reply=self._SAFE_REPLACEMENT,
                    category=ThreatCategory.PROMPT_INJECTION,
                )
        return GuardrailResult(blocked=False)
