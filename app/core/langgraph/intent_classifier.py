"""
Intent classification module for the travel planning agent.

Classifies user messages into intents using a combination of:
- Regex + keyword matching (for greeting, bye, feeling)
- LLM-based classification (for asking_information_user, search_flight, plan_travel, not_cover)

Priority rules handle multi-intent messages.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.prompts.system import INTENT_CLASSIFICATION_PROMPT
from app.core.langgraph.constants import (
    GREETING_PATTERNS,
    BYE_PATTERNS,
    PRAISE_PATTERNS,
    CRITICISM_PATTERNS,
    NEGATED_POSITIVE_PATTERNS,
    NEGATED_NEGATIVE_PATTERNS,
)
from app.schemas.intent_class import IntentType

logger = structlog.get_logger(__name__)

# Load direct responses from JSON file
_DIRECT_RESPONSES_PATH = Path(__file__).parent.parent.parent / "utter_responses/direct_responses.json"
with open(_DIRECT_RESPONSES_PATH, "r", encoding="utf-8") as f:
    DIRECT_RESPONSES: Dict[str, Dict[str, str]] = json.load(f)

# Priority order: higher priority intents override lower ones when multiple are detected
INTENT_PRIORITY = [
    IntentType.ASKING_INFORMATION_USER,
    IntentType.SEARCH_FLIGHT,
    IntentType.PLAN_TRAVEL,
    IntentType.FEELING,
    IntentType.GREETING,
    IntentType.BYE,
    IntentType.NOT_COVER,
]


def _match_patterns(text: str, patterns: List[str]) -> bool:
    """Check if text matches any of the given regex patterns."""
    text_lower = text.lower().strip()
    for pattern in patterns:
        if re.search(pattern, text_lower, re.IGNORECASE | re.UNICODE):
            return True
    return False


def classify_rule_based(text: str) -> List[Tuple[IntentType, Optional[str]]]:
    """
    Classify intent using regex and keyword matching.
    Returns a list of (intent, sub_label) tuples for all matched intents.
    sub_label is used for feeling: "praise" or "criticism".

    Negation-aware sentiment for Vietnamese:
      - "chưa giỏi" / "ko tốt"  → negation + positive = criticism
      - "ko ngu"    / "không gà" → negation + negative = praise
      - "giỏi quá"               → positive alone      = praise
      - "ngu quá"                → negative alone       = criticism
    """
    matched = []

    if _match_patterns(text, GREETING_PATTERNS):
        matched.append((IntentType.GREETING, None))

    if _match_patterns(text, BYE_PATTERNS):
        matched.append((IntentType.BYE, None))

    # ── Negation-aware feeling detection ──
    # Check negated patterns FIRST (they take priority over direct patterns)
    has_negated_positive = _match_patterns(text, NEGATED_POSITIVE_PATTERNS)  # "chưa giỏi" → criticism
    has_negated_negative = _match_patterns(text, NEGATED_NEGATIVE_PATTERNS)  # "ko ngu" → praise

    if has_negated_positive or has_negated_negative:
        # Negation detected — determine sentiment from the negation logic
        if has_negated_positive and not has_negated_negative:
            # "chưa giỏi", "ko tốt" → criticism
            matched.append((IntentType.FEELING, "criticism"))
        elif has_negated_negative and not has_negated_positive:
            # "ko ngu", "không gà" → praise
            matched.append((IntentType.FEELING, "praise"))
        else:
            # Both present — mixed signals, default to criticism
            matched.append((IntentType.FEELING, "criticism"))
    else:
        # No negation — use direct pattern matching
        has_direct_praise = _match_patterns(text, PRAISE_PATTERNS)
        has_direct_criticism = _match_patterns(text, CRITICISM_PATTERNS)

        if has_direct_criticism and has_direct_praise:
            # Both matched — criticism takes priority (safer assumption)
            matched.append((IntentType.FEELING, "criticism"))
        elif has_direct_criticism:
            matched.append((IntentType.FEELING, "criticism"))
        elif has_direct_praise:
            matched.append((IntentType.FEELING, "praise"))

    return matched


async def classify_with_llm(text: str) -> IntentType:
    """Use LLM to classify intent for complex messages."""
    try:
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=0,
            api_key=settings.OPENAI_API_KEY,
            max_tokens=20,
        )

        response = await llm.ainvoke([
            HumanMessage(content=INTENT_CLASSIFICATION_PROMPT.format(message=text))
        ])

        intent_text = response.content.strip().lower()

        intent_map = {
            "asking_information_user": IntentType.ASKING_INFORMATION_USER,
            "search_flight": IntentType.SEARCH_FLIGHT,
            "plan_travel": IntentType.PLAN_TRAVEL,
            "not_cover": IntentType.NOT_COVER,
        }

        return intent_map.get(intent_text, IntentType.NOT_COVER)

    except Exception as e:
        logger.error("llm_intent_classification_failed", error=str(e))
        # Fallback: route to agent (plan_travel) so the LLM can handle it
        return IntentType.PLAN_TRAVEL


def resolve_priority(intents: List[Tuple[IntentType, Optional[str]]]) -> Tuple[IntentType, Optional[str]]:
    """
    Given multiple detected intents, return the highest priority one.
    Priority order: asking_information_user > search_flight > plan_travel > feeling > greeting > bye > not_cover
    """
    if not intents:
        return (IntentType.NOT_COVER, None)

    if len(intents) == 1:
        return intents[0]

    intent_dict = {intent: sub for intent, sub in intents}

    for priority_intent in INTENT_PRIORITY:
        if priority_intent in intent_dict:
            return (priority_intent, intent_dict[priority_intent])

    return intents[0]


async def classify_intent(text: str) -> Tuple[IntentType, Optional[str]]:
    """
    Main classification function. Combines rule-based and LLM classification.

    Flow:
    1. Run regex/keyword matching for greeting, bye, feeling
    2. If ONLY simple intents matched (greeting/bye/feeling) and the message
       is short (likely standalone), return the rule-based result
    3. Otherwise, also run LLM classification and merge results with priority rules
    """
    rule_based_intents = classify_rule_based(text)

    simple_intents = {IntentType.GREETING, IntentType.BYE, IntentType.FEELING}
    rule_based_types = {intent for intent, _ in rule_based_intents}

    # If only simple intents detected and message is short, no need for LLM
    text_stripped = re.sub(r'[!.,?;\s]+', ' ', text).strip()
    word_count = len(text_stripped.split())

    if rule_based_intents and rule_based_types.issubset(simple_intents) and word_count <= 5:
        result = resolve_priority(rule_based_intents)
        logger.info("intent_classified", intent=result[0], method="rule_based", sub_label=result[1])
        return result

    # For longer/complex messages, or when no rule-based match, use LLM
    llm_intent = await classify_with_llm(text)
    all_intents = rule_based_intents + [(llm_intent, None)]

    result = resolve_priority(all_intents)
    logger.info("intent_classified", intent=result[0], method="hybrid", sub_label=result[1])
    return result


def generate_direct_response(intent: IntentType, sub_label: Optional[str] = None) -> Optional[str]:
    """
    Generate a direct response for intents that don't need LLM processing.
    Returns None if the intent should be handled by the agent.
    """
    intent_key = intent.name
    responses = DIRECT_RESPONSES.get(intent_key)

    if responses is None:
        # For ASKING_INFORMATION_USER, SEARCH_FLIGHT, PLAN_TRAVEL → handled by agent
        return None

    if sub_label and sub_label in responses:
        return responses[sub_label]

    return responses.get("default")
