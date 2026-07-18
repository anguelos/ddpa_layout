#!/usr/bin/env python3
"""DiDip layout serving app (mode 3) -- entry point.  Launch: ``ddpa_layout_serve``

The whole service is :class:`ddp_layout.layout_service.LayoutMicroservice` (a
``SharedIndexMicroservice`` from the didipcv core). This module is only the thin CLI wrapper:
construct the service (which parses the shared ``DdpMsConfigs`` config, reduces the FSDB into an
``FSDBLayoutIndex`` at load, and registers the ``/ly/...`` routes) and run it.

The previous procedural implementation (a module-level Flask ``app`` with its own ``load_seals``
reduce, ad-hoc ``Charter``/``Fond``/``Archive`` classes, hand-rolled sibling polling, and a dead
``main_ddp_seals_online``) has been replaced wholesale by the OO base + ``FSDBLayoutIndex``.
"""
from ddp_layout.layout_service import LayoutMicroservice


def main():
    LayoutMicroservice().run()


if __name__ == "__main__":
    main()
