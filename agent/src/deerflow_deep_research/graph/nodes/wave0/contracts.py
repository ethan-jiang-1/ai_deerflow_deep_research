from deerflow_deep_research.domain.lifecycle import FrozenContract, GateVerdict


class Wave0Request(FrozenContract):
    generation: int


class Wave0Result(FrozenContract):
    route: GateVerdict


CONTRACTS = (Wave0Request, Wave0Result)
