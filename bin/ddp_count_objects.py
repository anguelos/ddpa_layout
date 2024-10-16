#!/usr/bin/env python3

import glob
import fargv
import json
from pathlib import Path
from collections import defaultdict
import tqdm


def count_charter_objects(charter_path, filext=".seals.pred.json", min_width=501, min_height=501):
    seal_names = glob.glob(f"{charter_path}/*{filext}")
    outputs = []
    for seal_name in seal_names:
        data = json.load(open(seal_name, "r"))
        img_width = data["image_wh"][0]
        img_height = data["image_wh"][1]
        img_surface = img_width * img_height
        image_objects = []
        for n in range(len(data["rect_LTRB"])):
            rect_type = data["class_names"][data["rect_classes"][n]]
            rect_width = (data["rect_LTRB"][n][2] - data["rect_LTRB"][n][0]) + 1
            rect_height = (data["rect_LTRB"][n][3] - data["rect_LTRB"][n][1]) + 1
            image_objects.append((rect_width * rect_height, rect_type))
        seal_count = len([o for o in image_objects if o[1]=="Img:Seal"]) # This is the most important class
        if len(image_objects)>0:
            outputs.append((seal_count, img_surface, sorted(image_objects, reverse=True)[0][0], image_objects))
    if len(outputs) >0 :
        single_image_res = defaultdict(lambda: 0)
        selected_image = sorted(outputs, reverse=True)[0]
        for object_type in [o[1] for o in selected_image[3]]:
            single_image_res[object_type]+=1
        all_image_res = defaultdict(lambda: 0)
        seal_counts = []
        for seal_count, _, _, all_objects in outputs:
            seal_counts.append(seal_count)
            for _, object_type in all_objects:
                all_image_res[object_type]+=1
            
        return all_image_res, single_image_res, seal_counts
    else:
        return {}, {}, []

def count_statistics(charter_list):
    accumulate_all = defaultdict(lambda :0)
    accumulate_best = defaultdict(lambda :0)
    accumulate_seal_count = []
    accumulate_best_seal = []
    for charter_path in tqdm.tqdm(charter_list):
        all_image_res, single_image_res, seal_counts = count_charter_objects(charter_path=charter_path)
        for k, v in all_image_res.items():
            accumulate_all[k]+= v
        for k, v in single_image_res.items():
            accumulate_best[k]+= v
        accumulate_seal_count.extend(seal_counts)
    for k in accumulate_all:
        print(f"{k}:\t{accumulate_all[k]}, \t{accumulate_best[k]}")
    print(accumulate_best_seal)


p = {
    "charters": set([]),
    "charter_glob": ""
}

args, _ = fargv.fargv(p)

charters = list(args.charters) + list(glob.glob(args.charter_glob))

count_statistics(charters)
