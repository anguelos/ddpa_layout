How to perform Diplomatics experiments

** Download Data
```bash
pip install gdown
mkdir -p data/diplomatics
(cd data/diplomatics ;gdown https://drive.google.com/uc?id=1dGW0Ozo6Y5crckCcjYr_w93XewGm0p-y && tar -xpvzf train.tar.gz)
(cd data/diplomatics ;gdown https://drive.google.com/uc?id=11sX7LmeHqbGJUFTQ9kqJhKQ0zhXMDbvX && tar -xpvzf validate.tar.gz)
sed -i 's/..\/seal_ds\//.\/data\/diplomatics\//g' ./data/diplomatics/seal_ds.yaml
```


** Train Yolo
```bash
./bin/ddp_seals_train --data ./data/diplomatics/seal_ds.yaml --weights ''  --workers 0 --cfg ./models/yolo_didip.yaml --save-period 1
```

** View Training Results
```bash
ls ./runs/train/$(ls -Art ./runs/tr* | tail -n 1)
```

```bash
#PYTHONPATH="./" ./bin/ddp_seals_detect -weights ./runs/train/mytrain/weights/best.pt -img_paths /mnt/bkup/tmp/data/fsdb/*/*/*/*.img.*
PYTHONPATH="./legacy/:./"  ./bin/ddp_layout_detect -weights /home/anguelos/work/src/didipcv/misc/seals/yolov5/1Kimg.pt -img_paths ../maria_pia/tmp/ds/IT-BSNSP/*/*/*.jpg
```

** Run on the full database
```bash
export PYTHONPATH="$HOME/work/src/ddpa_layout"
export DBROOT="./"
echo "${DBROOT}"*/*/*/*.img.* | xargs -n 6000 ~/work/src/yolov5/bin/ddp_seals_detect -weights ~/work/src/ddpa_loyout/runs/train/mytrain/weights/best.pt -img_paths 
```

** Serve on FSDB
```bash
export PYTHONPATH="$HOME/work/src/ddpa_layout"
export DBROOT="../ddp_texture/data/lost_seals/"
./bin/ddp_layout_serve -root $DBROOT -debug 1
```
