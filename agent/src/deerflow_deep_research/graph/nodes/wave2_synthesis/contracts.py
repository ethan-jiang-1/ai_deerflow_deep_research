from deerflow_deep_research.domain.lifecycle import FrozenContract, SynthesisVerdict


class Wave2SynthesisRequest(FrozenContract):
    generation: int


class Wave2SynthesisResult(FrozenContract):
    route: SynthesisVerdict


CONTRACTS = (Wave2SynthesisRequest, Wave2SynthesisResult)
