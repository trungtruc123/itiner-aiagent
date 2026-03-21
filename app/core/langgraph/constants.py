# ─── Regex / keyword patterns ───────────────────────────────────────────────

GREETING_PATTERNS = [
    r"\b(hi|hello|helo|helllo|hey|chao|chaof|xin chao|chao bot|hi bot|xin chào|chào|chào bạn|chào anh|chào chị|helu|helo|alo)\b",
    r"^(hi|hello|hey|chào)[\s!.,]*$",
]

BYE_PATTERNS = [
    r"\b(bye|goodbye|byee|byeeee|tam biet|bye nghe|bye nge|tạm biệt|bye bye|bai bai|bái bai|hẹn gặp lại|see you|good night)\b",
    r"^(bye|tạm biệt|goodbye)[\s!.,]*$",
]

# Feeling: praise (khen) vs criticism (chê)
PRAISE_PATTERNS = [
    r"\b(tuyệt vời|tuyệt|giỏi|hay|tốt|xuất sắc|great|awesome|good job|good|nice|amazing|perfect|wonderful|cảm ơn|thank|thanks|nice|cool|love it|yêu|thích|棒)\b",
    r"\b(bạn giỏi|bạn tuyệt|rất tốt|rất hay|rất giỏi|quá giỏi|quá hay|quá tốt|quá đỉnh|bot giỏi)\b",
]

CRITICISM_PATTERNS = [
    r"\b(cùi|te|tệ|dot|dốt|ngu|gà|gaf|ga|dở|kém|chán|tồi|bad|terrible|awful|horrible|worst|sai|không tốt|không hay|không giỏi)\b",
    r"\b(bạn tệ|bạn dở|bạn kém|quá tệ|quá dở|quá kém|rất tệ|rất dở|như cứt|như c|như cc|quá gà|quá tệ|bot te qa|qa ga|non qua|non qa|tệ qá|dở quá|cùi qá|bot te|bot dở|bot ngu|bot gà|bot cùi)\b",
]
