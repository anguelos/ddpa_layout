"""Unit test for FSDBLayoutIndex (the layout-prediction reduce).

Builds a tiny synthetic FSDB (1 archive / 1 fond / 2 charters, 2 images, 2 prediction files),
reduces it, and checks the box arrays, the per-class inverted lists, basket scoping, and that
the charter/image/basket surface is correctly delegated to the composed FSDBSharedImageIndex.

Run standalone (no serving deps needed):
    PYTHONPATH=<didipcv>/src:<ddpa_layout> python3 test/layout/test_layout_index.py
"""
import json
import sys
import tempfile
from pathlib import Path

from ddp_layout.layout_index import FSDBLayoutIndex

ARCHIVE = "IT-Test"
FOND = "f" * 32
CH_A = "a" * 32
CH_B = "b" * 32
IMG1 = "1" * 32   # in charter A: 2 boxes (OldText, Seal)
IMG2 = "2" * 32   # in charter B: 1 box (OldText)


def _write_pred(charter_dir: Path, imgmd5: str, ltrbs, classes, confs, wh):
    (charter_dir / f"{imgmd5}.img.png").write_bytes(b"\x89PNG\r\n")  # a stand-in image file
    (charter_dir / f"{imgmd5}.layout.pred.json").write_text(json.dumps({
        "img_md5": imgmd5,
        "class_names": ["Wr:OldText", "Img:Seal"],
        "class_colors": ["#111111", "#222222"],
        "image_wh": wh,
        "rect_LTRB": ltrbs,
        "rect_classes": classes,
        "rect_captions": [f"$conf:{c}" for c in confs],
    }))


def build_fsdb(root: Path):
    a = root / ARCHIVE / FOND / CH_A
    b = root / ARCHIVE / FOND / CH_B
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    _write_pred(a, IMG1, [[10, 10, 20, 20], [30, 30, 40, 40]], [0, 1], [0.9, 0.8], [100, 200])
    _write_pred(b, IMG2, [[5, 5, 15, 15]], [0], [0.7], [50, 60])


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        build_fsdb(root)
        lay = FSDBLayoutIndex.from_fsdb_root(root)

        # box reduce
        assert lay.n_boxes == 3, lay.n_boxes
        assert dict(lay.class_cardinalities()) == {"Wr:OldText": 2, "Img:Seal": 1}, lay.class_cardinalities()

        # per-image boxes (CSR)
        assert len(lay.image_box_rows(IMG1)) == 2
        assert len(lay.image_box_rows(IMG2)) == 1

        # box_record identity + geometry
        rows1 = lay.image_box_rows(IMG1)
        recs = [lay.box_record(r) for r in rows1]
        assert {r["class_name"] for r in recs} == {"Wr:OldText", "Img:Seal"}
        assert all(r["imgmd5"] == IMG1 and r["charter_md5"] == CH_A for r in recs)
        assert {r["object_num"] for r in recs} == {0, 1}
        seal = next(r for r in recs if r["class_name"] == "Img:Seal")
        assert seal["LTRB"] == [30, 30, 40, 40] and abs(seal["confidence"] - 0.8) < 1e-6

        # per-class rows across the whole DB
        old = lay.class_box_rows("Wr:OldText")
        assert len(old) == 2
        assert {lay.box_record(r)["charter_md5"] for r in old} == {CH_A, CH_B}
        assert len(lay.class_box_rows("No:SuchClass")) == 0

        # basket scoping: restrict to charter A only -> just IMG1's OldText box
        mask_a = lay.receive_basket({"all_charters": False, "charter_ids": [CH_A],
                                     "fond_ids": [], "archive_ids": []})
        scoped = lay.class_box_rows("Wr:OldText", mask_a)
        assert len(scoped) == 1 and lay.box_record(scoped[0])["charter_md5"] == CH_A

        # all_charters basket == whole DB (no filter)
        mask_all = lay.receive_basket({"all_charters": True, "charter_ids": [], "fond_ids": [],
                                       "archive_ids": [], "bit_vector_hash": lay.index_hash})
        assert len(lay.class_box_rows("Wr:OldText", mask_all)) == 2

        # the /ly/charter data path: charter -> image rows -> boxes + wh
        irows = lay.charter_image_rows(CH_A)
        assert len(irows) == 1
        irow = int(irows[0])
        assert lay.image_id[irow].decode("ascii") == IMG1
        assert [int(x) for x in lay.image_wh[irow].tolist()] == [100, 200]
        assert len(lay.image_box_rows(irow)) == 2   # by image ROW (not md5)

        # delegation to the composed image index / charter namespace
        assert len(lay) == 2                       # charters
        assert CH_A in lay and CH_B in lay
        assert isinstance(lay.index_hash, str) and len(lay.index_hash) == 64
        assert isinstance(lay.to_db_bytes(), (bytes, bytearray))
        assert lay.image_path(IMG1).exists()
        assert lay.image_charter(IMG1) == CH_A
        assert lay.charter_path(CH_A).name == CH_A

    print("ok")


if __name__ == "__main__":
    main()
