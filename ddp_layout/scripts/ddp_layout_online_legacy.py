#!/usr/bin/env python3
"""LEGACY DiDip layout serving app (mode 3) -- entry point.  Launch: ``ddpa_layout_serve_legacy``

The whole service is :class:`ddp_layout.layout_service_legacy.LegacyLayoutMicroservice` (a
``SharedIndexMicroservice`` from the didipcv core). This module is only the thin CLI wrapper:
construct the service (which parses the shared ``DdpMsConfigs`` config, reduces the FSDB into an
``FSDBLayoutIndex`` at load, and registers the ``/ly/...`` routes) and run it.

Superseded by ``ddpa_layout_serve`` (the scope-aware ``sly`` service); kept so the ``ly`` prefix
and its rosters/bookmarks keep resolving.
"""
from ddp_layout.layout_service_legacy import LegacyLayoutMicroservice


def main():
    LegacyLayoutMicroservice().run()


if __name__ == "__main__":
    main()
