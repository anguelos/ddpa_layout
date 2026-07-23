"""The DiDip layout serving microservice (``sly``).

Launch (if not running):  ddpa_layout_serve

Layout analysis restricted to the **active basket**: the class overview and the by-class region
browser report what is in scope, not the whole database. It is the reference consumer of the
scoped-microservice layer in the didipcv core, so almost everything is inherited:

- ``@scoped_ms`` marks the service scope-aware; every route below is declared either
  ``@self.scoped_route`` (consumes the basket; GET+POST automatically) or
  ``@self.unscoped_route`` (ignores it -- a real scope there is rejected with 400). A plain
  ``@app.route`` would raise at startup, so each view states its relationship to the basket once.
- the basket itself never appears in a URL (it can be ~90 kB packed): ``static/ddp_scope.js``
  POSTs it and intercepts ``a.ddp-nav`` clicks, so ordinary ``create_pagers`` links keep their
  scope. Templates only ``{% include "_scope.html" %}`` and emit the ``#ddp-scope`` marker.
- ``self.reduce_for_request()`` returns the scoped summary when a basket is active and the
  memoised whole-DB one otherwise -- the views need no branch.

It owns the ``sly`` prefix, so it still runs beside the superseded whole-DB service
(:mod:`ddp_layout.layout_service_legacy`, ``ly``, ``ddpa_layout_serve_legacy``).

Compare ``tmp_scope_spike/tly_service.py``: the scope parsing, GET/POST wiring, navigation module
and pager were all hand-rolled there and are inherited here.
"""
from __future__ import annotations

import PIL.Image
from flask import jsonify, request, send_file

from ddp_util import create_pagers
from ddp_util.iiif.iiif import compute_iiif
from ddp_microservices import scope
from ddp_microservices.microservice import SharedIndexMicroservice, scoped_ms

from .config import MsLayout
from .layout_index import FSDBLayoutIndex


@scoped_ms
class LayoutMicroservice(SharedIndexMicroservice):
    """Layout regions browsable by class, scoped to the active basket.

    Launch (if not running):  ddpa_layout_serve
    """

    config_class = MsLayout
    GLOBAL_ROUTE_PREFIX = "sly"
    LAUNCH_CMD = "ddpa_layout_serve"
    VIEWS = ("charter", "root")
    index_class = FSDBLayoutIndex

    # ---- the reduce: generic counts (base) + the layout payload -------------------------
    def scoped_reduce(self, mask):
        """Base counts plus the by-class cardinalities, over the same charter mask.

        Reduces over compact numpy row arrays and emits only plain ints, so the result is
        JSON-serialisable and cheap enough to recompute per request -- ``global_reduce`` is this
        same call with an all-True mask (the whole DB), where materialising records would be
        impossible."""
        out = super().scoped_reduce(mask)
        rows_by_class = self.index.scoped_class_rows(mask)
        out["by_class"] = {name: int(len(rows)) for name, rows in rows_by_class.items()}
        out["total_objects"] = int(sum(out["by_class"].values()))
        return out

    def health_report(self) -> dict:
        rep = super().health_report()
        rep["n_boxes"] = self.index.n_boxes
        rep["n_classes"] = len(self.index.class_names)
        return rep

    # ---- routes ------------------------------------------------------------------------
    def register_routes(self):
        super().register_routes()                 # /sly/basket + /sly/basket/db
        page_itemcount = self.cfg.page_itemcount

        @self.scoped_route('/sly/')
        def home():
            """Landing page: the class overview, scoped to the active basket.
            ---
            responses:
              200: {description: class overview (html) or the summary (json)}
              409: {description: basket references a different index}
            """
            return classes()

        @self.scoped_route('/sly/classes')
        def classes():
            """Detected classes with their in-scope cardinalities.
            ---
            responses:
              200: {description: class overview (html) or the summary (json)}
              409: {description: basket references a different index}
            """
            summary = self.reduce_for_request()    # scoped when a basket is active, else global
            if (request.args.get('format') or 'html') == 'json':
                return jsonify(summary)
            rows = [(name, summary["by_class"][name]) for name in self.index.class_names]
            return self.render('layout_classes.html', rows=rows, summary=summary,
                               applied=scope.active)

        @self.scoped_route('/sly/classitems/<classname>')
        @self.scoped_route('/sly/classitems/<classname>/<int:skip>/<int:itemcount>')
        def classitems(classname, skip=0, itemcount=None):
            """One class's regions, paged, restricted to the active basket.
            ---
            responses:
              200: {description: paged regions (html or json)}
              409: {description: basket references a different index}
            """
            itemcount = itemcount or page_itemcount
            rows = self.index.class_box_rows(classname, scope.charters if scope.active else None)
            total = int(len(rows))
            first, prev, current, following, last = create_pagers(total, skip, itemcount)
            begin = current[0]
            # materialise ONLY the visible page (the scoped rows may be millions)
            items = [self.index.box_record(int(r)) for r in rows[begin:begin + current[1]]]
            if (request.args.get('format') or 'html') == 'json':
                return jsonify({"classname": classname, "total": total, "skip": skip,
                                "itemcount": itemcount, "items": items})
            return self.render('layout_classitems.html', classname=classname, items=items,
                               total=total, first=first, prev=prev, current=current,
                               following=following, last=last, applied=scope.active)

        @self.unscoped_route('/sly/charter/<md5>')
        def charter(md5):
            """Layout-annotated charter view (a single charter: the basket does not narrow it).
            ---
            responses:
              200: {description: annotated charter page}
              404: {description: unknown charter}
            """
            if md5 not in self.index:
                return f"Unknown charter {md5}", 404
            images = []
            for irow in self.index.charter_image_rows(md5):
                irow = int(irow)
                images.append({
                    "imgmd5": self.index.image_id[irow].decode('ascii'),
                    "wh": [int(x) for x in self.index.image_wh[irow].tolist()],
                    "objects": [self.index.box_record(int(r))
                                for r in self.index.image_box_rows(irow)],
                })
            return self.render('layout_charter.html', charter_md5=md5, images=images,
                               sibling_md5=md5)

        @self.unscoped_route('/sly/iiif/<md5>')
        @self.unscoped_route('/sly/iiif/<md5>/<region>')
        @self.unscoped_route('/sly/iiif/<md5>/<region>/<size>')
        @self.unscoped_route('/sly/iiif/<md5>/<region>/<size>/<rotation>')
        @self.unscoped_route('/sly/iiif/<md5>/<region>/<size>/<rotation>/<quality>')
        @self.unscoped_route('/sly/iiif/<md5>/<region>/<size>/<rotation>/<quality>.<format>')
        def serve_iiif(md5, region="full", size="max", rotation="0", quality="default", format="jpg"):
            """Self-hosted IIIF Image API for a charter image (so sly runs without Static).
            ---
            responses:
              200: {description: transformed image}
              404: {description: unknown image}
            """
            try:
                img_path = self.index.image_path(md5)
            except (KeyError, FileNotFoundError):
                return f"Unknown image {md5}", 404
            buffer, mimetype = compute_iiif(PIL.Image.open(str(img_path)), md5, region, size=size,
                                            rotation=rotation, quality=quality, format=format)
            return send_file(buffer, mimetype=mimetype)
