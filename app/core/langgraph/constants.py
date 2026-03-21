# ─── Regex / keyword patterns ───────────────────────────────────────────────

GREETING_PATTERNS = [
    r"\b(hi|hello|helo|helllo|hey|chao|chaof|xin chao|chao bot|hi bot|xin chào|chào|chào bạn|chào anh|chào chị|helu|helo|alo)\b",
    r"^(hi|hello|hey|chào)[\s!.,]*$",
]

BYE_PATTERNS = [
    r"\b(bye|goodbye|byee|byeeee|tam biet|bye nghe|bye nge|tạm biệt|bye bye|bai bai|bái bai|hẹn gặp lại|see you|good night)\b",
    r"^(bye|tạm biệt|goodbye)[\s!.,]*$",
]

# ─── Feeling: negation-aware sentiment detection ────────────────────────────
#
# Vietnamese negation words flip sentiment:
#   "chưa giỏi" (not yet good) = criticism, NOT praise
#   "ko ngu"    (not dumb)     = praise, NOT criticism
#
# Strategy:
#   1. NEGATION_WORDS matches: chưa, không, ko, chẳng, chả, đâu có, k, hong, hông, kg, kog
#   2. POSITIVE_WORDS: words that are inherently positive (giỏi, tốt, hay, ...)
#   3. NEGATIVE_WORDS: words that are inherently negative (tệ, ngu, gà, dở, ...)
#   4. Logic:
#       - negation + positive_word → criticism  ("chưa tốt" = criticism)
#       - negation + negative_word → praise     ("ko ngu" = praise)
#       - positive_word alone      → praise     ("giỏi quá" = praise)
#       - negative_word alone      → criticism  ("ngu quá" = criticism)

NEGATION_PREFIXES = r"(?:chưa|chua|không|khong|ko|k|chẳng|chang|chả|cha|đâu có|dau co|hong|hông|kg|kog|kh)"

# Positive words (without negation = praise, with negation = criticism)
POSITIVE_WORDS = (
    r"giỏi|gioi|tốt|tot|hay|tuyệt|tuyet|tuyệt vời|tuyet voi|xuất sắc|xuat sac"
    r"|ngon|đỉnh|dinh|xịn|xin|pro|good|great|awesome|amazing|perfect|wonderful|nice|cool"
    r"|được|duoc|ổn|on|khá|kha"
)

# Negative words (without negation = criticism, with negation = praise)
NEGATIVE_WORDS = (
    r"tệ|te|dở|do|kém|kem|ngu|gà|ga|gaf|cùi|cui|tồi|toi|dốt|dot|chán|chan"
    r"|bad|terrible|awful|horrible|worst"
    r"|bình thường|binh thuong|non"
)

# Patterns that detect negation + positive → criticism
# Example: "chưa giỏi", "ko tốt", "không hay"
NEGATED_POSITIVE_PATTERNS = [
    rf"\b{NEGATION_PREFIXES}\s+(?:được\s+)?(?:{POSITIVE_WORDS})\b",
]

# Patterns that detect negation + negative → praise
# Example: "ko ngu", "không gà", "chẳng tệ"
NEGATED_NEGATIVE_PATTERNS = [
    rf"\b{NEGATION_PREFIXES}\s+(?:có\s+)?(?:{NEGATIVE_WORDS})\b",
]

# Direct praise patterns (no negation involved)
PRAISE_PATTERNS = [
    r"\b(thông minh|thong minh|tuyệt vời|tuyệt|xuất sắc|great|awesome|good job|amazing|perfect|wonderful|cảm ơn|thank|thanks|love it|yêu|thích)\b",
    r"\b(được quá|bot được quá|bot dc qua|bạn giỏi|bạn tuyệt|rất tốt|rất hay|rất giỏi|quá giỏi|quá hay|quá tốt|quá đỉnh|bot giỏi|giỏi quá|tốt quá|hay quá|xịn quá|đỉnh quá|pro quá)\b",
    r"\b(giỏi|hay|tốt|ngon|đỉnh|xịn|pro|good|nice|cool)\b",
]

# Direct criticism patterns (no negation involved)
CRITICISM_PATTERNS = [
    r"\b(cùi|tệ|dốt|ngu|gà|dở|kém|chán|tồi|bad|terrible|awful|horrible|worst|sai)\b",
    r"\b(bạn tệ|bạn dở|bạn kém|quá tệ|quá dở|quá kém|rất tệ|rất dở|như cứt|như c|như cc|quá gà|bot te qa|qa ga|non qua|non qa|tệ quá|dở quá|cùi quá|bot tệ|bot dở|bot ngu|bot gà|bot cùi|bình thường quá|bot bình thường|tệ lắm|dở lắm|kém lắm)\b",
]
