"""Layout-prediction index for the DiDip layout serving app.

``FSDBLayoutIndex`` is built by **composition** over
:class:`fsdb.shared_index.FSDBSharedImageIndex`: it HOLDS an image index (the charter/
fond/archive namespace, the per-image universe, and the baskets/wire container) and adds the
layout payload reduced at load from the per-image ``<imgmd5>.layout.pred.json`` files that
``ddpa_layout_offline`` writes -- the detection boxes (LTRB, class, confidence) flattened and
aligned to the image universe, plus per-class inverted lists that power the ``/classitems``
browser.

Only ``fsdb`` + ``numpy`` are imported here (no Flask), so the reduce is unit-testable without
a serving environment. The whole charter/image/basket surface of the inner index is delegated
(``__getattr__`` for attributes/methods, explicit ``__len__`` / ``__contains__`` for the dunder
calls Python resolves on the type), so an ``FSDBLayoutIndex`` satisfies everything the
``SharedIndexMicroservice`` base and the ``/basket`` blueprint expect of an ``FSDBSharedIndex``
(``index_hash``, ``archive_id`` / ``fond_id``, ``fsdb_root``, ``filepattern``, ``to_db_bytes``,
``charter_path``, ``send_basket`` / ``receive_basket`` ...).

Boxes, like images, stay server-side: the wire basket is charter-md5 based (inherited), so a
scope selection resolves to a charter set and slices the boxes locally.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from glob import glob
from pathlib import Path

import numpy as np
from tqdm import tqdm

from fsdb.shared_index import FSDBSharedIndex, FSDBSharedImageIndex

#: charter-relative glob for the per-image layout prediction files (one per charter image).
LAYOUT_PRED_GLOB = "*.layout.pred.json"


def _confidence(caption) -> float:
    """Parse a ``rect_captions`` entry (``"$conf:0.53..."``) to a float; NaN if absent/garbage."""
    try:
        return float(str(caption).split("$conf:")[-1])
    except (TypeError, ValueError):
        return float("nan")


class FSDBLayoutIndex:
    """Layout boxes reduced over an FSDB, composed with an ``FSDBSharedImageIndex``.

    Independent state (all aligned so ``box`` rows index the flat arrays):

    - ``class_names`` / ``class_colors`` : the global class registry, built by NAME as files are
      read (never by a file's local index -- model versions may reorder classes).
    - ``box_ltrb`` ``float32[M,4]`` (pixel Left,Top,Right,Bottom in the original image),
      ``box_class`` ``int32[M]`` (-> ``class_names``), ``box_conf`` ``float32[M]``.
    - ``box_image_row`` ``int32[M]`` / ``box_charter_row`` ``int32[M]`` : owning image / charter
      rows in the inner index's sorted universes.
    - ``image_box_start`` ``int32[Ni+1]`` : CSR offsets so image row ``r``'s boxes are
      ``[start[r]:start[r+1]]`` (boxes are laid out in image-row order).
    - ``image_wh`` ``int32[Ni,2]`` : each image's (width, height) from its prediction file (0,0
      when the image has no predictions).
    """

    def __init__(self, image_index, *, class_names, class_colors, box_ltrb, box_class,
                 box_conf, box_image_row, box_charter_row, image_box_start, image_wh):
        self._img = image_index
        self.class_names = list(class_names)
        self.class_colors = list(class_colors)
        self.box_ltrb = np.asarray(box_ltrb, dtype="<f4").reshape(-1, 4)
        self.box_class = np.asarray(box_class, dtype="<i4")
        self.box_conf = np.asarray(box_conf, dtype="<f4")
        self.box_image_row = np.asarray(box_image_row, dtype="<i4")
        self.box_charter_row = np.asarray(box_charter_row, dtype="<i4")
        self.image_box_start = np.asarray(image_box_start, dtype="<i4")
        self.image_wh = np.asarray(image_wh, dtype="<i4").reshape(-1, 2)
        # per-class inverted lists: class idx -> sorted global box rows (drives /classitems).
        self._class_rows = {ci: np.where(self.box_class == ci)[0].astype("<i4")
                            for ci in range(len(self.class_names))}
        self._class_of_name = {name: ci for ci, name in enumerate(self.class_names)}

    # ---- construction ------------------------------------------------------------------
    #: ``<imgmd5>.layout.pred.json`` -- the prediction file sits beside ``<imgmd5>.img.<ext>`` in
    #: the charter dir, so both are read in the SAME scandir pass (see ``_scan_images_and_preds``).
    _PRED_RE = re.compile(r"^([0-9a-f]{32})\.layout\.pred\.json$")

    @classmethod
    def from_fsdb_root(cls, fsdb_root, *, filepattern=None, verbose=0):
        """Build the charter namespace (fast dir-name crawl) then read the image files AND their
        layout prediction files in a SINGLE pass -- one ``os.scandir`` per charter dir, no
        separate walk for predictions. Signature matches ``FSDBSharedIndex.from_fsdb_root`` so
        ``SharedIndexMicroservice`` can use this as its ``index_class``. ``filepattern`` is
        forwarded to the inner index's optional presence overlay."""
        base = FSDBSharedIndex.from_fsdb_root(fsdb_root, filepattern=filepattern, verbose=verbose)
        image_id, image_ext, image_to_charter_idx, collected = cls._scan_images_and_preds(base, verbose=verbose)
        img = FSDBSharedImageIndex(
            base.archive_id, base.fond_id, base.charter_id,
            base.charter_to_fond_idx, base.fond_to_archive_idx,
            image_id=image_id, image_to_charter_idx=image_to_charter_idx, image_ext=image_ext,
            filepattern=base.filepattern, presence_mask=base.presence_mask, fsdb_root=base.fsdb_root)
        return cls._assemble(img, collected, verbose=verbose)

    @classmethod
    def from_image_index(cls, img, *, verbose=0):
        """Alternate build when an ``FSDBSharedImageIndex`` already exists: read the prediction
        files by globbing the tree (a SECOND pass over the charter dirs). Prefer
        :meth:`from_fsdb_root`, which fuses the image and prediction reads into one scandir."""
        if img.fsdb_root is None:
            raise ValueError("layout reduce requires the image index to know its fsdb_root")
        collected: dict[str, tuple[list, tuple]] = {}
        for jp in glob(f"{Path(img.fsdb_root)}/*/*/*/{LAYOUT_PRED_GLOB}"):
            rec = cls._read_pred(jp)
            if rec is not None:
                imgmd5, boxes, wh = rec
                collected[imgmd5] = (boxes, wh)
        return cls._assemble(img, collected, verbose=verbose)

    @classmethod
    def _scan_images_and_preds(cls, base, *, verbose=0):
        """One pass over the charter dirs known to ``base``: a single ``os.scandir`` per dir that
        collects both ``<md5>.img.<ext>`` image files and ``<md5>.layout.pred.json`` predictions.
        Returns ``(image_id, image_ext, image_to_charter_idx, collected)`` where the image arrays
        match what ``FSDBSharedImageIndex`` expects (sorted by image md5) and ``collected`` maps
        image md5 -> ``(boxes, wh)`` with name-based boxes (class indexing happens in _assemble)."""
        if base.fsdb_root is None:
            raise ValueError("layout scan requires the charter index to know its fsdb_root")
        root = Path(base.fsdb_root)
        img_re, pred_re = FSDBSharedImageIndex._IMG_RE, cls._PRED_RE
        t0 = time.time()
        if verbose >= 1:
            print(f"[FSDBLayoutIndex] scanning images + layout predictions in {len(base)} charters ...",
                  file=sys.stderr, flush=True)
        positions = range(len(base))
        if verbose >= 2:
            positions = tqdm(positions, unit="charter", desc="[FSDBLayoutIndex] scanning", file=sys.stderr)

        img_ids: list[str] = []
        img_pos: list[int] = []
        img_exts: list[str] = []
        collected: dict[str, tuple[list, tuple]] = {}
        for pos in positions:
            cdir = root / base.charter_relpath(pos)
            try:
                with os.scandir(cdir) as it:
                    for e in it:
                        if not e.is_file():
                            continue
                        m = img_re.match(e.name)
                        if m:
                            img_ids.append(m.group(1))
                            img_pos.append(pos)
                            img_exts.append(m.group(2))
                            continue
                        mp = pred_re.match(e.name)
                        if mp:
                            rec = cls._read_pred(e.path, imgmd5=mp.group(1))
                            if rec is not None:
                                imgmd5, boxes, wh = rec
                                collected[imgmd5] = (boxes, wh)
            except OSError:
                pass

        if img_ids:
            image_md5_arr = np.array(img_ids, dtype="S32")
            iorder = np.argsort(image_md5_arr, kind="stable")
            image_id = np.ascontiguousarray(image_md5_arr[iorder])
            image_ext = np.ascontiguousarray(np.array(img_exts, dtype="S")[iorder])
            image_to_charter_idx = np.array(img_pos, dtype="<i4")[iorder]
        else:
            image_id = np.empty(0, dtype="S32")
            image_ext = np.empty(0, dtype="S1")
            image_to_charter_idx = np.empty(0, dtype="<i4")

        if verbose >= 1:
            print(f"[FSDBLayoutIndex] found {len(image_id)} images + {len(collected)} prediction "
                  f"files in {time.time() - t0:.2f}s", file=sys.stderr, flush=True)
        return image_id, image_ext, image_to_charter_idx, collected

    @staticmethod
    def _read_pred(path, imgmd5=None):
        """Read one ``*.layout.pred.json`` into ``(imgmd5, boxes, wh)`` with **name-based** boxes
        ``(ltrb, class_name, class_color, conf)`` -- resolving classes by the file's OWN
        ``class_names`` (never a hard-coded index). Returns ``None`` on a missing/broken file."""
        try:
            d = json.load(open(path))
        except (OSError, ValueError):
            return None
        if imgmd5 is None:
            imgmd5 = d.get("img_md5") or Path(path).name.split(".")[0]
        names = d.get("class_names", [])
        colors = d.get("class_colors", [])
        rect_ltrb = d.get("rect_LTRB", [])
        rect_classes = d.get("rect_classes", [])
        captions = d.get("rect_captions", [])
        boxes = []
        for i in range(len(rect_ltrb)):
            ci = rect_classes[i]
            name = names[ci] if ci < len(names) else str(ci)
            color = colors[ci] if ci < len(colors) else "#888888"
            conf = _confidence(captions[i]) if i < len(captions) else float("nan")
            boxes.append((rect_ltrb[i], name, color, conf))
        wh = tuple(d.get("image_wh", (0, 0)))[:2]
        return imgmd5, boxes, (wh if len(wh) == 2 else (0, 0))

    @classmethod
    def _assemble(cls, img, collected, *, verbose=0):
        """Build the global class registry (by NAME, so model-version reorderings don't matter)
        and flatten the per-image boxes into CSR arrays aligned to ``img``'s sorted image
        universe. Shared by both build paths."""
        t0 = time.time()
        class_names: list[str] = []
        class_colors: list[str] = []
        class_of_name: dict[str, int] = {}

        def class_idx(name, color):
            j = class_of_name.get(name)
            if j is None:
                j = class_of_name[name] = len(class_names)
                class_names.append(name)
                class_colors.append(color)
            return j

        ni = img.n_images
        box_ltrb: list = []
        box_class: list = []
        box_conf: list = []
        box_image_row: list = []
        box_charter_row: list = []
        image_box_start = np.zeros(ni + 1, dtype="<i4")
        image_wh = np.zeros((ni, 2), dtype="<i4")
        img_ids = [m.decode("ascii") for m in img.image_id.tolist()]
        for r in range(ni):
            boxes, wh = collected.get(img_ids[r], ([], (0, 0)))
            image_wh[r] = wh
            crow = int(img.image_to_charter_idx[r])
            for (ltrb, name, color, conf) in boxes:
                box_ltrb.append(ltrb)
                box_class.append(class_idx(name, color))
                box_conf.append(conf)
                box_image_row.append(r)
                box_charter_row.append(crow)
            image_box_start[r + 1] = image_box_start[r] + len(boxes)

        if verbose >= 1:
            print(f"[FSDBLayoutIndex] {len(box_class)} boxes / {len(class_names)} classes over "
                  f"{len(collected)} annotated images in {time.time() - t0:.2f}s", file=sys.stderr, flush=True)

        return cls(img, class_names=class_names, class_colors=class_colors,
                   box_ltrb=np.array(box_ltrb, dtype="<f4").reshape(-1, 4) if box_ltrb else np.empty((0, 4), "<f4"),
                   box_class=box_class, box_conf=box_conf, box_image_row=box_image_row,
                   box_charter_row=box_charter_row, image_box_start=image_box_start, image_wh=image_wh)

    # ---- inner-index delegation --------------------------------------------------------
    @property
    def image_index(self):
        """The composed :class:`FSDBSharedImageIndex` (charter/image namespace + baskets)."""
        return self._img

    def __getattr__(self, name):
        # only reached for attributes NOT found on FSDBLayoutIndex itself -> delegate to the
        # inner index (index_hash, archive_id, fond_id, fsdb_root, filepattern, to_db_bytes,
        # charter_path, image_path, image_charter, send_basket, receive_basket, ...).
        return getattr(self._img, name)

    def __len__(self):
        return len(self._img)               # charters (dunder: resolved on the type, not __getattr__)

    def __contains__(self, md5):
        return md5 in self._img

    # ---- box namespace -----------------------------------------------------------------
    @property
    def n_boxes(self) -> int:
        return int(len(self.box_class))

    def class_index_of(self, name) -> int:
        """Class name -> global class index, or -1 if unknown."""
        return self._class_of_name.get(name, -1)

    def class_cardinalities(self) -> list[tuple[str, int]]:
        """``[(class_name, box_count), ...]`` in registry order (for the ``/classes`` view)."""
        return [(name, int(len(self._class_rows[ci]))) for ci, name in enumerate(self.class_names)]

    def image_box_rows(self, imgmd5) -> np.ndarray:
        """Global box rows of an image md5 (or image row), in file order. Empty if none."""
        r = self._img._image_position(imgmd5) if not isinstance(imgmd5, (int, np.integer)) else int(imgmd5)
        return np.arange(self.image_box_start[r], self.image_box_start[r + 1], dtype="<i4")

    def class_box_rows(self, class_name, charter_mask=None) -> np.ndarray:
        """Global box rows of a class, optionally restricted to a charter selection.

        ``charter_mask`` is a bool array over the charter universe (what
        ``FSDBSharedIndex.receive_basket`` returns); ``None`` means the whole DB (no filter)."""
        ci = self._class_of_name.get(class_name, -1)
        if ci < 0:
            return np.empty(0, dtype="<i4")
        rows = self._class_rows[ci]
        if charter_mask is None:
            return rows
        mask = np.asarray(charter_mask, dtype=bool)
        return rows[mask[self.box_charter_row[rows]]]

    def box_record(self, row) -> dict:
        """A rich, JSON-serialisable record for one global box row: identity + geometry."""
        row = int(row)
        irow = int(self.box_image_row[row])
        crow = int(self.box_charter_row[row])
        cidx = int(self.box_class[row])
        object_num = row - int(self.image_box_start[irow])   # the Nth box of its image
        return {
            "row": row,
            "object_num": object_num,
            "imgmd5": self._img.image_id[irow].decode("ascii"),
            "charter_md5": self._img.charter_id[crow].decode("ascii"),
            "class_name": self.class_names[cidx],
            "class_color": self.class_colors[cidx],
            "confidence": float(self.box_conf[row]),
            "LTRB": [int(x) for x in self.box_ltrb[row].tolist()],
        }
