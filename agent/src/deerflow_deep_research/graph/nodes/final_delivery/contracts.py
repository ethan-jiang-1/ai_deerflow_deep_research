from deerflow_deep_research.domain.lifecycle import FinalVerdict, FrozenContract


class FinalDeliveryRequest(FrozenContract):
    generation: int


class FinalDeliveryResult(FrozenContract):
    route: FinalVerdict
    terminal_fixture_marker: str | None = None


CONTRACTS = (FinalDeliveryRequest, FinalDeliveryResult)
