from enum import Enum


class IntentType(str, Enum):
    GREETING = "greeting"
    BYE = "bye"
    FEELING = "feeling"
    ASKING_INFORMATION_USER = "asking_information_user"
    SEARCH_FLIGHT = "search_flight"
    PLAN_TRAVEL = "plan_travel"
    NOT_COVER = "not_cover"
