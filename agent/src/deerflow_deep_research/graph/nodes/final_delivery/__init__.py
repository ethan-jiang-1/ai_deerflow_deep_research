from deerflow_deep_research.domain.enums import NodePhase
from deerflow_deep_research.domain.node_spec import NodeContracts, NodeSpec, PolicyRef

from .contracts import CONTRACTS as _CONTRACTS
from .fake import build_fake as _build_fake
from .node import build_real as _build_real

NODE_SPEC = NodeSpec(
    logical_name="final_delivery",
    phase=NodePhase.PUBLICATION,
    policy=PolicyRef(name="skeleton-final-delivery", version="v1"),
    contracts=NodeContracts(request_type=_CONTRACTS[0], result_type=_CONTRACTS[1]),
    real_factory=_build_real,
    fake_factory=_build_fake,
)
__all__ = ["NODE_SPEC"]
