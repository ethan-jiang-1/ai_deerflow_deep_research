"""Pure final-publication store interface.

@impl FID-001
@impl FID-002
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from deerflow_deep_research.domain.state import ContentRef


@runtime_checkable
class PublicationBundleStoreProtocol(Protocol):
    async def publish_final(self, report: bytes, citation_map: bytes) -> tuple[ContentRef, ContentRef]: ...


__all__ = ["PublicationBundleStoreProtocol"]
