from deerflow_deep_research.domain.lifecycle import BootstrapRoute, FrozenContract


class BootstrapRequest(FrozenContract):
    request_text: str


class BootstrapResult(FrozenContract):
    route: BootstrapRoute
    marker_ref: str | None = None


CONTRACTS = (BootstrapRequest, BootstrapResult)
