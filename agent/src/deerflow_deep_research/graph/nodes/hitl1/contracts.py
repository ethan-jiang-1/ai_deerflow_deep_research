from typing import Literal

from deerflow_deep_research.domain.lifecycle import FrozenContract


class Hitl1Request(FrozenContract):
    request_text: str


class Hitl1Result(FrozenContract):
    route: Literal["accepted", "cancel", "needs_followup", "exhausted"]


CONTRACTS = (Hitl1Request, Hitl1Result)
