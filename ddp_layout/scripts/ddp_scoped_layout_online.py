#!/usr/bin/env python3
"""SCOPED DiDip layout serving app (mode 3) -- entry point.  Launch: ``ddpa_scoped_layout_serve``

Thin CLI wrapper: the whole service is
:class:`ddp_layout.scoped_layout_service.ScopedLayoutMicroservice` (a ``@scoped_ms``
``SharedIndexMicroservice`` from the didipcv core). It owns the ``sly`` prefix, so it can run
beside the original ``ly`` service (``ddpa_layout_serve``) during the transition.
"""
from ddp_layout.scoped_layout_service import ScopedLayoutMicroservice


def main():
    ScopedLayoutMicroservice().run()


if __name__ == "__main__":
    main()
