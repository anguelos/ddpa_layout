"""Config for the LEGACY layout serving app (``ly``) — the app OWNS it.

Same decentralized pattern as :mod:`ddp_layout.config` (subclass the shared
``DdpMsConfigs.Microservice`` base; do NOT join the central suite). This is the superseded
whole-DB layout service, launched as ``ddpa_layout_serve_legacy``; it keeps the ``ly`` prefix and
``ms_id = 3`` (reserved for layout in the core) so existing rosters, bookmarks and ``/ly/...``
links keep resolving to it while the scope-aware service (:mod:`ddp_layout.config`, ``sly``) is
the one behind ``ddpa_layout_serve``.
"""
from ddp_util.config_ms import DdpMsConfigs


class MsLegacyLayout(DdpMsConfigs.Microservice):
    ms_id: int = 3
    icon: str = "static/icon_layout.svg"
    route_prefix: str = "ly"
    launch_cmd: str = "ddpa_layout_serve_legacy"
    page_itemcount: int = 25
    "default number of regions per page in the /ly/classitems browser (when the URL omits it)."
