"""TraceSphere Platform (member B).

ZSvirt integration + resource model + correlation engine + evidence store.

Modules
-------
- :mod:`tsplatform.zsvirt`   ZSvirt REST / Fixture providers (one domain model)
- :mod:`tsplatform.store`    SQLite WAL stores (resources / events / evidence / agents)
- :mod:`tsplatform.registry` Resource Registry (provider sync -> resources + graph)
- :mod:`tsplatform.ingest`   Event ingest (Schema v1 normalize + identity enrichment)
- :mod:`tsplatform.correlate` Cross-signal correlation (time window + resource + topology)
- :mod:`tsplatform.api`      HTTP API (``/api/v1/*``)
"""

__version__ = "0.1.0"
SCHEMA_VERSION = "v1"
