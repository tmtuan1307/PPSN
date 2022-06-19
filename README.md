# Code
Perceptual Position-aware Shapelet Network (Accepted to ECML PKDD 2022)

![alt text](https://github.com/tmtuan1307/ppsn/blob/eaa2a622e669daf6663a21e4fd81b706752f6b0d/ppsn.png)

## Dependencies
- pytorch 1.11.0 and above

## Usage
We provide the demo of ECGFiveDays in the UCR dataset.  The ECGFiveDays dataset is located in `dataset/UCRArchive_2018/ECGFiveDays/`. You can run the command
```
python ppsn_demo.py
```
to test the model.

# Classification Result
You can see the full results on 112 UCR datasets in `results/`, in that `results/ppsn_vs_sbc.csv` contains the results of PPSN and other Shapelet-based Classifiers, while `results/ppsn_vs_sota.csv` contains the results of SOTA methods.
