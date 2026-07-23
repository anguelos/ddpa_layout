"""Layout serving-app configuration — the app OWNS it (decentralized microservice pattern).

``MsLayout`` subclasses the shared ``DdpMsConfigs.Microservice`` base (from the didipcv core) but
is **not** a member of the central ``DdpMsConfigs`` suite: an app declares its own service without
editing the core. fargv parses it with ``suite_root=DdpMsConfigs`` (see
``DidipMicroservice.parse_config``), so it inherits ``fsdb_root`` / ``base_port`` / ``bind`` /
``proxy_url`` / ``monitor_frequency`` / … and adds the layout-specific fields.

This is the config of the **current** layout service (``ddpa_layout_serve``), which is
scope-aware: every listing it serves is restricted to the active basket. It owns the ``sly``
prefix and ``ms_id = 9``. The superseded whole-DB service kept ``ly`` / ``ms_id = 3`` — see
:mod:`ddp_layout.config_legacy` — so the two can still run side by side.

Note: an out-of-suite subclass's OWN fields are not exposed as CLI flags — only the inherited base
fields are. Anything that must be settable from the command line (``--workers``, ``--fsdb_root``,
``--proxy_url`` …) therefore lives on ``DdpMsConfigs.Microservice`` in didipcv.
"""
from ddp_util.config_ms import DdpMsConfigs


class MsLayout(DdpMsConfigs.Microservice):
    ms_id: int = 9
    icon: str = "static/icon_layout.svg"
    route_prefix: str = "sly"
    launch_cmd: str = "ddpa_layout_serve"
    page_itemcount: int = 100
    "default number of regions per page in the /sly/classitems browser (when the URL omits it)."
