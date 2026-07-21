"""Config for the SCOPED layout serving app (``sly``) — the app OWNS it.

Same decentralized pattern as :mod:`ddp_layout.config` (subclass the shared
``DdpMsConfigs.Microservice`` base; do NOT join the central suite), but it owns the ``sly`` prefix
so it can run **beside** the original ``ly`` service during the transition.

Note: an out-of-suite subclass's OWN fields are not exposed as CLI flags — only the inherited base
fields are. Anything that must be settable from the command line (``--workers``, ``--fsdb_root``,
``--proxy_url`` …) therefore lives on ``DdpMsConfigs.Microservice`` in didipcv.
"""
from ddp_util.config_ms import DdpMsConfigs


class MsScopedLayout(DdpMsConfigs.Microservice):
    ms_id: int = 9
    icon: str = "static/icon_layout.svg"
    route_prefix: str = "sly"
    launch_cmd: str = "ddpa_scoped_layout_serve"
    page_itemcount: int = 100
    "default number of regions per page in the /sly/classitems browser (when the URL omits it)."
