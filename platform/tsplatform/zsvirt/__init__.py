"""ZSvirt package: REST + Fixture providers sharing one domain model."""

from .base import EdgeRecord, ResourceRecord, Snapshot, ZSvirtProvider
from .fixture import FixtureProvider
from .rest import RESTProvider, ZSvirtRestClient, ZSvirtError

__all__ = [
    "EdgeRecord",
    "ResourceRecord",
    "Snapshot",
    "ZSvirtProvider",
    "FixtureProvider",
    "RESTProvider",
    "ZSvirtRestClient",
    "ZSvirtError",
]
