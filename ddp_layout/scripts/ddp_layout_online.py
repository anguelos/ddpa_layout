#!/usr/bin/env python3
"""DiDip layout serving app (mode 3) -- entry point.  Launch: ``ddpa_layout_serve``

Thin CLI wrapper: the whole service is :class:`ddp_layout.layout_service.LayoutMicroservice`
(a ``@scoped_ms`` ``SharedIndexMicroservice`` from the didipcv core), which restricts every
listing to the active basket. It owns the ``sly`` prefix, so it runs beside the superseded
whole-DB service (``ddpa_layout_serve_legacy``, ``/ly/...``).
"""
from ddp_layout.layout_service import LayoutMicroservice


def main():
    LayoutMicroservice().run()


if __name__ == "__main__":
    main()
