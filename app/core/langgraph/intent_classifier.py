"""
Intent classification module for the travel planning agent.

Classifies user messages into intents using a combination of:
- Regex + keyword matching (for greeting, bye, feeling)
- LLM-based classification (for asking_information_user, search_flight, plan_travel, not_cover)

Priority rules handle multi-intent messages.
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.metrics import AGENT_STEP_COUNT
from app.core.prompts.system import INTENT_CLASSIFICATION_PROMPT
from app.core.langgraph.constants import *
from app.schemas.intent_class import IntentType

logger = structlog.get_logger(__name__)

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
    """
    matched = []

    if _match_patterns(text, GREETING_PATTERNS):
        matched.append((IntentType.GREETING, None))

    if _match_patterns(text, BYE_PATTERNS):
        matched.append((IntentType.BYE, None))

    is_praise = _match_patterns(text, PRAISE_PATTERNS)
    is_criticism = _match_patterns(text, CRITICISM_PATTERNS)
    if is_praise or is_criticism:
        sub_label = "praise" if is_praise else "criticism"
        matched.append((IntentType.FEELING, sub_label))

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
    if intent == IntentType.GREETING:
        return "Xin chào! Tôi là trợ lý du lịch AI. Tôi có thể giúp bạn tìm chuyến bay, đặt khách sạn, gợi ý điểm đến và lên kế hoạch du lịch. Bạn cần tôi giúp gì?"

    if intent == IntentType.BYE:
        return "Tạm biệt! Chúc bạn có chuyến đi vui vẻ. Hẹn gặp lại!"

    if intent == IntentType.FEELING:
        if sub_label == "praise":
            return "Cảm ơn bạn đã khen! Tôi rất vui khi có thể giúp ích cho bạn. Bạn cần tôi hỗ trợ thêm gì không?"
        else:
            return "Mình sẽ cố gắng nhiều hơn để hỗ trợ bạn tốt hơn. Bạn có thể cho tôi biết cần giúp gì thêm không?"

    if intent == IntentType.NOT_COVER:
        return "Xin lỗi, câu hỏi này nằm ngoài phạm vi của bot. Tôi chỉ có thể hỗ trợ về du lịch, tìm chuyến bay, đặt khách sạn và gợi ý điểm đến. Bạn cần tôi giúp gì về du lịch không?"

    # For ASKING_INFORMATION_USER, SEARCH_FLIGHT, PLAN_TRAVEL → handled by agent
    return None
