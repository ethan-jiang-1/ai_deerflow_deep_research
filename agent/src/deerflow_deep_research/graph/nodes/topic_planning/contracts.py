from typing import Literal

from deerflow_deep_research.domain.lifecycle import FrozenContract


class TopicPlanningRequest(FrozenContract):
    request_text: str


class TopicPlanningResult(FrozenContract):
    route: Literal["next"] = "next"


CONTRACTS = (TopicPlanningRequest, TopicPlanningResult)
