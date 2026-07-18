"""Layout serving-app configuration — the app OWNS it (decentralized microservice pattern).

``MsLayout`` subclasses the shared ``DdpMsConfigs.Microservice`` base (from the didipcv core) but
is **not** a member of the central ``DdpMsConfigs`` suite: an app declares its own service without
editing the core. fargv parses it with ``suite_root=DdpMsConfigs`` (see
``DidipMicroservice.parse_config``), so it inherits ``fsdb_root`` / ``base_port`` / ``bind`` /
``proxy_url`` / ``monitor_frequency`` / … and adds the layout-specific fields. ``ms_id = 3`` is
reserved for layout in the core.
"""
from ddp_util.config_ms import DdpMsConfigs


class MsLayout(DdpMsConfigs.Microservice):
    ms_id: int = 3
    icon: str = "static/icon_layout.svg"
    route_prefix: str = "ly"
    launch_cmd: str = "ddpa_layout_serve"
    page_itemcount: int = 25
    "default number of regions per page in the /ly/classitems browser (when the URL omits it)."
