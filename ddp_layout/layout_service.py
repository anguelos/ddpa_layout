#!/usr/bin/env python3
"""The DiDip layout serving microservice (``ms_id=3``), as a :class:`SharedIndexMicroservice`.

Launch (if not running):  ddpa_layout_serve

This brings the layout app's online mode onto the current DiDip standard: it subclasses the
OO base in the ``didipcv`` core (``ddp_microservices``), so it inherits ``/ly/health`` +
``/ly/info`` + ``/ly/health_report``, Swagger, sibling discovery/monitor, ``run()``, and the
shared ``/ly/basket`` + ``/ly/basket/db`` routes. ``self.index`` is an :class:`FSDBLayoutIndex`
(composition over ``FSDBSharedImageIndex``) reduced from the ``*.layout.pred.json`` files.

It owns the layout-specific surface under its ``/ly`` prefix (own-the-prefix): ``/ly/classes``,
``/ly/classitems`` (the class-item browser, scoped by the active basket), ``/ly/objects``,
``/ly/charter`` (the layout-annotated charter view) and a self-hosted ``/ly/iiif`` (so the app
runs without Static). Every class-item / object thumbnail carries ``data-charter-md5`` so it can
be dragged into the basket (see the shared ``ddp_drag.js`` + the basket widget's drop target).

Depends on the ``didipcv`` core (``ddp_microservices`` / ``ddp_util`` / ``fsdb``); install it
into the serving venv. Flask, PIL and numpy come in via those. Nothing is imported lazily.
"""
from __future__ import annotations

import PIL.Image
from flask import jsonify, request, send_file

from ddp_util import create_pagers
from ddp_util.iiif.iiif import compute_iiif
from ddp_microservices import scope
from ddp_microservices.microservice import SharedIndexMicroservice

from .config import MsLayout
from .layout_index import FSDBLayoutIndex


class LayoutMicroservice(SharedIndexMicroservice):
    """Layout-analysis serving app: browse detected regions by class, scoped by a basket.

    Launch (if not running):  ddpa_layout_serve
    """

    config_class = MsLayout                      # app-owned config (ddp_layout/config.py), not the core suite
    GLOBAL_ROUTE_PREFIX = "ly"                    # every route is /ly/... (own-the-prefix)
    LAUNCH_CMD = "ddpa_layout_serve"
    VIEWS = ("charter", "root")                  # hand-off view types layout accepts (/ly/charter, /ly/)
    filepattern = None                           # the box reduce globs the prediction files itself
    index_class = FSDBLayoutIndex

    # ---- health_report: add the layout payload sizes ----------------------------------
    def health_report(self) -> dict:
        rep = super().health_report()
        rep["n_boxes"] = self.index.n_boxes
        rep["n_classes"] = len(self.index.class_names)
        return rep

    # ---- routes ------------------------------------------------------------------------
    def register_routes(self):
        super().register_routes()                # /ly/basket + /ly/basket/db
        app = self.app
        page_itemcount = self.cfg.page_itemcount   # single source of truth: MsLayout config

        @app.route('/ly/classes')
        def serve_classes():
            """All layout classes with their box cardinalities (whole DB).
            ---
            responses:
              200: {description: class list (json) or a table (html)}
            """
            if (request.args.get('format') or 'html') == 'json':
                return jsonify(self.index.class_names)
            return self.render('layout_classes.html', data=self.index.class_cardinalities())

        @app.route('/ly/classitems/<classname>')
        @app.route('/ly/classitems/<classname>/<int:skip>/<int:itemcount>')
        def serve_classitems(classname, skip=0, itemcount=None):
            """Boxes of one class, paged, scoped to the active basket (?scope=<wire basket>).
            ---
            responses:
              200: {description: paged class items (json or html)}
              409: {description: basket references a different index}
            """
            itemcount = itemcount or page_itemcount
            # inherited request-scoped basket: the charter mask when a scope is active, else None
            # (whole DB, fast path). A different-index basket -> 409 via the base error handler.
            mask = scope.charters if scope.active else None
            rows = self.index.class_box_rows(classname, mask)
            total = int(len(rows))
            first, prev, current, following, last = create_pagers(total, skip, itemcount)
            begin, end = current[0], min(current[0] + current[1], total)
            records = [self.index.box_record(int(r)) for r in rows[begin:end]]
            if (request.args.get('format') or 'html') == 'json':
                return jsonify({"classname": classname, "total": total, "items": records})
            return self.render('layout_classitems.html', classname=classname, items=records,
                               total=total, first=first, prev=prev, current=current,
                               following=following, last=last)

        @app.route('/ly/objects/<imgmd5>/<int:object_num>')
        def serve_object(imgmd5, object_num):
            """One detected object (the Nth box of an image).
            ---
            responses:
              200: {description: object record (json or html)}
              404: {description: unknown image or object index}
            """
            try:
                rows = self.index.image_box_rows(imgmd5)
            except KeyError:
                return f"Unknown image {imgmd5}", 404
            if not 0 <= object_num < len(rows):
                return f"No object {object_num} in image {imgmd5}", 404
            rec = self.index.box_record(int(rows[object_num]))
            if (request.args.get('format') or 'html') == 'json':
                return jsonify(rec)
            return self.render('layout_object.html', obj=rec)

        @app.route('/ly/charter/<md5>')
        def render_charter(md5):
            """Layout-annotated charter view: each image with its detected boxes overlaid.
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
                imgmd5 = self.index.image_id[irow].decode('ascii')
                wh = [int(x) for x in self.index.image_wh[irow].tolist()]
                objects = [self.index.box_record(int(r)) for r in self.index.image_box_rows(irow)]
                images.append({"imgmd5": imgmd5, "wh": wh, "objects": objects})
            return self.render('layout_charter.html', charter_md5=md5, images=images,
                               sibling_md5=md5)

        @app.route('/ly/iiif/<md5>')
        @app.route('/ly/iiif/<md5>/<region>')
        @app.route('/ly/iiif/<md5>/<region>/<size>')
        @app.route('/ly/iiif/<md5>/<region>/<size>/<rotation>')
        @app.route('/ly/iiif/<md5>/<region>/<size>/<rotation>/<quality>')
        @app.route('/ly/iiif/<md5>/<region>/<size>/<rotation>/<quality>.<format>')
        def serve_iiif(md5, region="full", size="max", rotation="0", quality="default", format="jpg"):
            """Self-hosted IIIF Image API for a charter image (so layout runs without Static).
            ---
            responses:
              200: {description: transformed image}
              404: {description: unknown image}
            """
            try:
                img_path = self.index.image_path(md5)
            except (KeyError, FileNotFoundError):
                return f"Unknown image {md5}", 404
            pil_image = PIL.Image.open(str(img_path))
            buffer, mimetype = compute_iiif(pil_image, md5, region, size=size, rotation=rotation,
                                            quality=quality, format=format)
            return send_file(buffer, mimetype=mimetype)

        @app.route('/ly/')
        def home():
            """Landing page: the class list.
            ---
            responses:
              200: {description: home / class list}
            """
            return self.render('layout_classes.html', data=self.index.class_cardinalities())
