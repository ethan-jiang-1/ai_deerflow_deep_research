from deerflow_deep_research.domain.enums import NodePhase
from deerflow_deep_research.domain.node_spec import NodeCapability, NodeContracts, NodeSpec, PolicyRef

from .contracts import CONTRACTS as _CONTRACTS
from .fake import build_fake as _build_fake
from .node import build_real as _build_real

NODE_SPEC = NodeSpec(
    logical_name="hitl1",
    phase=NodePhase.ORCHESTRATION,
    policy=PolicyRef(name="skeleton-hitl1", version="v1"),
    contracts=NodeContracts(request_type=_CONTRACTS[0], result_type=_CONTRACTS[1]),
    real_factory=_build_real,
    fake_factory=_build_fake,
    capabilities=frozenset({NodeCapability.REQUEST_BUNDLE}),
)
__all__ = ["NODE_SPEC"]
