"""Safe loader for the MELT dataset (git-disl/MELT).

feature.pkl is a pickle from the internet: NEVER pickle.load() it directly. This loader
only allows numpy array reconstruction and OrderedDict; any other global (os.system,
subprocess, ...) raises. Do not widen ALLOW without reading the file's opcodes first.
"""
import pickle

import numpy as np
import pandas as pd

ALLOW = {
    ("collections", "OrderedDict"), ("numpy", "dtype"), ("numpy", "ndarray"),
    ("numpy.core.multiarray", "scalar"), ("numpy.core.multiarray", "_reconstruct"),
    ("numpy.core.numeric", "_frombuffer"), ("numpy._core.multiarray", "scalar"),
    ("numpy._core.multiarray", "_reconstruct"), ("numpy._core.numeric", "_frombuffer"),
}


class _SafeUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if (module, name) in ALLOW:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"blocked global {module}.{name}")


def load_features(pkl_path):
    with open(pkl_path, "rb") as f:
        records = _SafeUnpickler(f).load()
    rows = [{k: v for k, v in r.items() if np.ndim(v) == 0} for r in records]
    return pd.DataFrame(rows)


def load_dataset(pkl_path, label_csv):
    feats = load_features(pkl_path)
    labels = pd.read_csv(label_csv)
    df = feats.merge(labels, on="mint_address", how="inner")
    return df
