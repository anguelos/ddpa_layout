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

