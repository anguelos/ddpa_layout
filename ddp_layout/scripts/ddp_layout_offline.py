#!/usr/bin/env python3

import sys
import torch
from torch import cpu
import ddp_layout
import fargv
from dataclasses import dataclass
from ddp_layout import utils
from PIL import Image
import torchvision
# import yolov5.utils.general
from pathlib import Path
from ddp_layout.models.common import DetectMultiBackend
from ddp_layout.utils.plots import colors, Annotator, save_one_box
from ddp_layout.utils.general import non_max_suppression
import cv2
import hashlib
import subprocess
import json
import tqdm
import re
import glob
import fsdb


have_highgui = "GUI:                           NONE" not in cv2.getBuildInformation()


def get_md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def get_git_repo_strs():
    try:
        remote = subprocess.check_output(
            "git config --get remote.origin.url", shell=True).strip().decode("utf-8")
        head_str = subprocess.check_output(
            'git rev-parse HEAD', shell=True).strip().decode("utf-8")
    except:
        remote = "unknown"
        head_str = "unknown"
    return remote, head_str


def create_frat_userid(app_name, weigths_path):
    return f"app:{app_name},git:{repr(get_git_repo_strs())},weights:{get_md5(weigths_path)}"


def main_ddp_seals_offline():
    @fargv.deep_dataclass
    class Args(fsdb.CharterImageFargvConfig):
        appname: str = "layout"
        output_replace: str = ".{appname}.pred.json"
        imgsz: int = 1024
        frat_comment_begin_marker: str = "$"
        weights: str = "/home/anguelos_ro/work/src/didipcv.bkup/misc/seals/yolov5/1Kimg.pt"
        classes: str = '["No Class", "Ignore", "Img:CalibrationCard", "Img:Seal", "Img:WritableArea", "Wr:OldText", "Wr:OldNote", "Wr:NewText", "Wr:NewOther", "WrO:Ornament", "WrO:Fold"]'
        class_colors: str = '["#646B63","#23282B","#763C28","#316650","#00BB2D","#287233","#231A24","#F5D033","#063971","#1E2460","#641C34"]'
        crop_classes: str = '["Wr:OldText"]'
        device: str = "cpu"
        conf_thres: float = 0.25
        iou_thres: float = 0.45
        max_det: int = 1000
        preview_delay: int = 1000


    args, _ = fargv.parse(Args)
    input2output = fsdb.FsdbOutputInferer(args)

    model = DetectMultiBackend(
        weights=args.weights, device=torch.device(args.device))
    model = model.float()

    print(f"Model: {model.names}, Classes: {args.classes}")
    assert len(model.names) == len(eval(args.classes))

    model.names = eval(args.classes)

    imgsz = utils.general.check_img_size(args.imgsz)  # check image size

    from ddp_layout.utils.datasets import LoadImages

    images_list = list(fsdb.generate_image_paths(args, verbosity=args.verbosity))
    if len(images_list) == 0:
        print("No images to be processed found. Check the input paths and filters.")
        return
    dl = LoadImages(images_list, imgsz, 32)

    dt, seen = [0.0, 0.0, 0.0], 0

    names = eval(args.classes)
    class_colors = eval(args.class_colors)

    if args.verbosity > 2 and have_highgui:
        cv2.namedWindow("Seals")
        cv2.resizeWindow("Seals", 1700, 800)
    else:
        print("Highgui not available, cannot show preview windows. Install OpenCV with GUI support to enable this feature.", file=sys.stderr)

    frat_user_str = create_frat_userid(args.appname, args.weights)
    if args.verbosity > 0:
        progress = tqdm.tqdm(dl)
    else:
        progress = dl
    for path, im, im0s, vid_cap, s in progress:
        if args.verbosity > 1:
            progress.set_description(f"{Path(path).name}")
            progress.refresh()
        im = torch.from_numpy(im).to(args.device)
        # print("im.size():",im.size(),"  im0s.size()",im0s.shape)
        # im = im.half() if model.fp16 else im.float()  # uint8 to fp16/32
        im = im.float()
        im /= 255  # 0 - 255 to 0.0 - 1.0
        if len(im.shape) == 3:
            im = im[None]  # expand for batch dim
        pred = model(im)
        
        #pred = ddp_layout.utils.general.non_max_suppression(pred[0], conf_thres=args.conf_thres, iou_thres=args.iou_thres, classes=None, max_det=args.max_det)

        pred = non_max_suppression(pred, conf_thres=args.conf_thres,
                                   iou_thres=args.iou_thres, classes=None, max_det=args.max_det)
        frat_dict = {"img_md5": get_md5(path), "user": frat_user_str,
                     "class_names": names, "class_colors": class_colors,
                     "image_wh": [im0s.shape[1], im0s.shape[0]],
                     "rect_LTRB": [], "rect_captions": [], "rect_classes": []}

        for i, det in enumerate(pred):  # per image
            seen += 1
            p, im0, frame = path, im0s.copy(), getattr(dl, 'frame', 0)

            p = Path(p)  # to Path
            save_dir = Path("/tmp")
            save_path = str(save_dir / p.name)  # im.jpg
            txt_path = str(save_dir / 'labels' / p.stem) + \
                ('' if dl.mode == 'image' else f'_{frame}')  # im.txt
            s += '%gx%g ' % im.shape[2:]  # print string

            gn = torch.tensor(im0.shape)[[1, 0, 1, 0]]

            annotator = Annotator(im0, line_width=4, example=str(names))

            if len(det):
                # Rescale boxes from img_size to im0 size
                from ddp_layout.utils.general import scale_coords
                det[:, :4] = scale_coords(
                    im.shape[2:], det[:, :4], im0.shape).round()

                # Print results
                for c in det[:, -1].unique():
                    n = (det[:, -1] == c).sum()  # detections per class
                    s = 's'
                    s += f"{n} {names[int(c)]}{s * (n > 1)}"
                save_txt = False
                save_img = True
                hide_labels = False
                hide_conf = False
                for n, (*xyxy, conf, cls) in enumerate(reversed(det)):
                    frat_dict["rect_LTRB"].append(
                        torch.tensor(xyxy).to("cpu").numpy().tolist())
                    frat_dict["rect_captions"].append(
                        f"{args.frat_comment_begin_marker}conf:{conf}")
                    frat_dict["rect_classes"].append(int(cls))

                    # if save_img or args.save_crops or args.preview:  # Add bbox to image
                    #     c = int(cls)  # integer class
                    #     label = None if hide_labels else (
                    #         names[c] if hide_conf else f'{names[c]} {conf:.2f}')
                    #     annotator.box_label(xyxy, label, color=colors(c, True))
                    #     if args.save_crops and names[int(cls)] in eval(args.crop_classes):
                    #         class_clean_name = re.sub(
                    #             r'[^a-zA-Z0-9]', '_', names[int(cls)])
                    #         class_dir_path = replace_img_basename(
                    #             path, f".{args.appname}.crops")
                    #         # print("CLass Dir Path",repr(class_dir_path),"\n\n")
                    #         # class_dir_path.mkdir(parents=True, exist_ok=True)
                    #         crop_path = Path(
                    #             f"{class_dir_path}/{n}.{class_clean_name}.jpg")
                    #         save_one_box(xyxy, im0s.copy(),
                    #                      file=crop_path, BGR=True)

            # Stream results
            im0 = annotator.result()
            if args.verbosity > 2 and have_highgui:
                cv2.imshow("Seals", cv2.resize(im0, (1600, 850)))
                cv2.resizeWindow("Seals", 1700, 900)
                cv2.moveWindow("Seals", 50, 50)
                cv2.waitKey(args.preview_delay)
        if args.verbosity > 2 and have_highgui:
            cv2.destroyAllWindows()

        output_path = input2output(path)
        if args.verbosity > 1:
            print(f"Saving to {output_path}")
        open(output_path, "w").write(json.dumps(frat_dict, indent=2))
