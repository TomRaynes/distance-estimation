
import sys
import os
import json
import logging
import numpy as np
import cv2
import onnxruntime
from utils import get_onnxruntime_providers, DownloadableWeights


class DPT(DownloadableWeights):
    def __init__(self):
        self._model_loaded = False

    def _load_model(self):
        if self._model_loaded:
            return
        self._model_loaded = True

        weights_url = "https://github.com/timmh/DPT/releases/download/onnx_v0.1/dpt_hybrid-midas-6c3ec701.onnx"
        weights_md5 = "2e9e68ad03f4c519e3624ab181ffe888"
        weights_path = self.get_weights(weights_url, weights_md5)

        providers = get_onnxruntime_providers()

        num_threads = int(os.getenv('SLURM_CPUS_PER_TASK', '28'))

        sess_options = onnxruntime.SessionOptions()
        sess_options.intra_op_num_threads = num_threads
        sess_options.inter_op_num_threads = num_threads

        try:
            self.session = onnxruntime.InferenceSession(
                weights_path,
                providers=providers,
            )
        except Exception as e:
            providers_str = ",".join(providers)
            logging.warn(f"Failed to create onnxruntime inference session with providers '{providers_str}', trying 'CPUExecutionProvider'")
            self.session = onnxruntime.InferenceSession(
                weights_path,
                providers=["CPUExecutionProvider"],
            )

        metadata = self.session.get_modelmeta().custom_metadata_map
        self.net_w, self.net_h = json.loads(metadata["ImageSize"])
        normalization = json.loads(metadata["Normalization"])
        self.prediction_factor = float(metadata["PredictionFactor"])
        self.mean = np.array(normalization["mean"])
        self.std = np.array(normalization["std"])
    
    def __call__(self, img):
        # ensure model is loaded
        self._load_model()

        # BGR to RGB
        img = img[..., ::-1]

        # convert into 0..1 range
        img = img / 255.

        # resize
        img_input = cv2.resize(img, (self.net_w, self.net_h), cv2.INTER_AREA)

        # normalize
        img_input = (img_input - self.mean) / self.std

        # transpose from HWC to CHW
        img_input = img_input.transpose(2, 0, 1)

        # add batch dimension
        img_input = img_input[None, ...]

        # compute
        prediction = self.session.run(["output"], {"input": img_input.astype(np.float32)})[0][0]
        prediction = cv2.resize(prediction, (img.shape[1], img.shape[0]), cv2.INTER_CUBIC)
        prediction *= self.prediction_factor

        return prediction