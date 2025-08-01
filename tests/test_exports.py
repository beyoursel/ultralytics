# Ultralytics 🚀 AGPL-3.0 License - https://ultralytics.com/license

import io
import shutil
import uuid
from contextlib import redirect_stderr, redirect_stdout
from itertools import product
from pathlib import Path

import pytest

from tests import MODEL, SOURCE
from ultralytics import YOLO
from ultralytics.cfg import TASK2DATA, TASK2MODEL, TASKS
from ultralytics.utils import (
    ARM64,
    IS_RASPBERRYPI,
    LINUX,
    MACOS,
    WINDOWS,
    checks,
)
from ultralytics.utils.torch_utils import TORCH_1_9, TORCH_1_13


def test_export_torchscript():
    """Test YOLO model export to TorchScript format for compatibility and correctness."""
    file = YOLO(MODEL).export(format="torchscript", optimize=False, imgsz=32)
    YOLO(file)(SOURCE, imgsz=32)  # exported model inference


def test_export_onnx():
    """Test YOLO model export to ONNX format with dynamic axes."""
    file = YOLO(MODEL).export(format="onnx", dynamic=True, imgsz=32)
    YOLO(file)(SOURCE, imgsz=32)  # exported model inference


@pytest.mark.skipif(not TORCH_1_13, reason="OpenVINO requires torch>=1.13")
def test_export_openvino():
    """Test YOLO export to OpenVINO format for model inference compatibility."""
    file = YOLO(MODEL).export(format="openvino", imgsz=32)
    YOLO(file)(SOURCE, imgsz=32)  # exported model inference


@pytest.mark.slow
@pytest.mark.skipif(not TORCH_1_13, reason="OpenVINO requires torch>=1.13")
@pytest.mark.parametrize(
    "task, dynamic, int8, half, batch, nms",
    [  # generate all combinations except for exclusion cases
        (task, dynamic, int8, half, batch, nms)
        for task, dynamic, int8, half, batch, nms in product(
            TASKS, [True, False], [True, False], [True, False], [1, 2], [True, False]
        )
        if not ((int8 and half) or (task == "classify" and nms))
    ],
)
def test_export_openvino_matrix(task, dynamic, int8, half, batch, nms):
    """Test YOLO model export to OpenVINO under various configuration matrix conditions."""
    file = YOLO(TASK2MODEL[task]).export(
        format="openvino",
        imgsz=32,
        dynamic=dynamic,
        int8=int8,
        half=half,
        batch=batch,
        data=TASK2DATA[task],
        nms=nms,
    )
    if WINDOWS:
        # Use unique filenames due to Windows file permissions bug possibly due to latent threaded use
        # See https://github.com/ultralytics/ultralytics/actions/runs/8957949304/job/24601616830?pr=10423
        file = Path(file)
        file = file.rename(file.with_stem(f"{file.stem}-{uuid.uuid4()}"))
    YOLO(file)([SOURCE] * batch, imgsz=64 if dynamic else 32, batch=batch)  # exported model inference
    shutil.rmtree(file, ignore_errors=True)  # retry in case of potential lingering multi-threaded file usage errors


@pytest.mark.slow
@pytest.mark.parametrize(
    "task, dynamic, int8, half, batch, simplify, nms",
    [  # generate all combinations except for exclusion cases
        (task, dynamic, int8, half, batch, simplify, nms)
        for task, dynamic, int8, half, batch, simplify, nms in product(
            TASKS, [True, False], [False], [False], [1, 2], [True, False], [True, False]
        )
        if not ((int8 and half) or (task == "classify" and nms) or (task == "obb" and nms and not TORCH_1_13))
    ],
)
def test_export_onnx_matrix(task, dynamic, int8, half, batch, simplify, nms):
    """Test YOLO export to ONNX format with various configurations and parameters."""
    file = YOLO(TASK2MODEL[task]).export(
        format="onnx", imgsz=32, dynamic=dynamic, int8=int8, half=half, batch=batch, simplify=simplify, nms=nms
    )
    YOLO(file)([SOURCE] * batch, imgsz=64 if dynamic else 32)  # exported model inference
    Path(file).unlink()  # cleanup


@pytest.mark.slow
@pytest.mark.parametrize(
    "task, dynamic, int8, half, batch, nms",
    [  # generate all combinations except for exclusion cases
        (task, dynamic, int8, half, batch, nms)
        for task, dynamic, int8, half, batch, nms in product(TASKS, [False], [False], [False], [1, 2], [True, False])
        if not (task == "classify" and nms)
    ],
)
def test_export_torchscript_matrix(task, dynamic, int8, half, batch, nms):
    """Test YOLO model export to TorchScript format under varied configurations."""
    file = YOLO(TASK2MODEL[task]).export(
        format="torchscript", imgsz=32, dynamic=dynamic, int8=int8, half=half, batch=batch, nms=nms
    )
    YOLO(file)([SOURCE] * batch, imgsz=64 if dynamic else 32)  # exported model inference
    Path(file).unlink()  # cleanup


@pytest.mark.slow
@pytest.mark.skipif(not MACOS, reason="CoreML inference only supported on macOS")
@pytest.mark.skipif(not TORCH_1_9, reason="CoreML>=7.2 not supported with PyTorch<=1.8")
@pytest.mark.skipif(checks.IS_PYTHON_3_13, reason="CoreML not supported in Python 3.13")
@pytest.mark.parametrize(
    "task, dynamic, int8, half, batch",
    [  # generate all combinations except for exclusion cases
        (task, dynamic, int8, half, batch)
        for task, dynamic, int8, half, batch in product(TASKS, [False], [True, False], [True, False], [1])
        if not (int8 and half)
    ],
)
def test_export_coreml_matrix(task, dynamic, int8, half, batch):
    """Test YOLO export to CoreML format with various parameter configurations."""
    file = YOLO(TASK2MODEL[task]).export(
        format="coreml",
        imgsz=32,
        dynamic=dynamic,
        int8=int8,
        half=half,
        batch=batch,
    )
    YOLO(file)([SOURCE] * batch, imgsz=32)  # exported model inference
    shutil.rmtree(file)  # cleanup


@pytest.mark.slow
@pytest.mark.skipif(not checks.IS_PYTHON_MINIMUM_3_10, reason="TFLite export requires Python>=3.10")
@pytest.mark.skipif(
    not LINUX or IS_RASPBERRYPI,
    reason="Test disabled as TF suffers from install conflicts on Windows, macOS and Raspberry Pi",
)
@pytest.mark.parametrize(
    "task, dynamic, int8, half, batch, nms",
    [  # generate all combinations except for exclusion cases
        (task, dynamic, int8, half, batch, nms)
        for task, dynamic, int8, half, batch, nms in product(
            TASKS, [False], [True, False], [True, False], [1], [True, False]
        )
        if not ((int8 and half) or (task == "classify" and nms) or (ARM64 and nms))
    ],
)
def test_export_tflite_matrix(task, dynamic, int8, half, batch, nms):
    """Test YOLO export to TFLite format considering various export configurations."""
    file = YOLO(TASK2MODEL[task]).export(
        format="tflite", imgsz=32, dynamic=dynamic, int8=int8, half=half, batch=batch, nms=nms
    )
    YOLO(file)([SOURCE] * batch, imgsz=32)  # exported model inference
    Path(file).unlink()  # cleanup


@pytest.mark.skipif(not TORCH_1_9, reason="CoreML>=7.2 not supported with PyTorch<=1.8")
@pytest.mark.skipif(WINDOWS, reason="CoreML not supported on Windows")  # RuntimeError: BlobWriter not loaded
@pytest.mark.skipif(LINUX and ARM64, reason="CoreML not supported on aarch64 Linux")
@pytest.mark.skipif(checks.IS_PYTHON_3_13, reason="CoreML not supported in Python 3.13")
def test_export_coreml():
    """Test YOLO export to CoreML format and check for errors."""
    # Capture stdout and stderr
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        YOLO(MODEL).export(format="coreml", nms=True, imgsz=32)
        if MACOS:
            file = YOLO(MODEL).export(format="coreml", imgsz=32)
            YOLO(file)(SOURCE, imgsz=32)  # model prediction only supported on macOS for nms=False models

    # Check captured output for errors
    output = stdout.getvalue() + stderr.getvalue()
    assert "Error" not in output, f"CoreML export produced errors: {output}"
    assert "You will not be able to run predict()" not in output, "CoreML export has predict() error"


@pytest.mark.skipif(not checks.IS_PYTHON_MINIMUM_3_10, reason="TFLite export requires Python>=3.10")
@pytest.mark.skipif(not LINUX, reason="Test disabled as TF suffers from install conflicts on Windows and macOS")
def test_export_tflite():
    """Test YOLO export to TFLite format under specific OS and Python version conditions."""
    model = YOLO(MODEL)
    file = model.export(format="tflite", imgsz=32)
    YOLO(file)(SOURCE, imgsz=32)


@pytest.mark.skipif(True, reason="Test disabled")
@pytest.mark.skipif(not LINUX, reason="TF suffers from install conflicts on Windows and macOS")
def test_export_pb():
    """Test YOLO export to TensorFlow's Protobuf (*.pb) format."""
    model = YOLO(MODEL)
    file = model.export(format="pb", imgsz=32)
    YOLO(file)(SOURCE, imgsz=32)


@pytest.mark.skipif(True, reason="Test disabled as Paddle protobuf and ONNX protobuf requirements conflict.")
def test_export_paddle():
    """Test YOLO export to Paddle format, noting protobuf conflicts with ONNX."""
    YOLO(MODEL).export(format="paddle", imgsz=32)


@pytest.mark.slow
def test_export_mnn():
    """Test YOLO export to MNN format (WARNING: MNN test must precede NCNN test or CI error on Windows)."""
    file = YOLO(MODEL).export(format="mnn", imgsz=32)
    YOLO(file)(SOURCE, imgsz=32)  # exported model inference


@pytest.mark.slow
def test_export_ncnn():
    """Test YOLO export to NCNN format."""
    file = YOLO(MODEL).export(format="ncnn", imgsz=32)
    YOLO(file)(SOURCE, imgsz=32)  # exported model inference


@pytest.mark.skipif(True, reason="Test disabled as keras and tensorflow version conflicts with TFlite export.")
@pytest.mark.skipif(not LINUX or MACOS, reason="Skipping test on Windows and Macos")
def test_export_imx():
    """Test YOLO export to IMX format."""
    model = YOLO("yolov8n.pt")
    file = model.export(format="imx", imgsz=32)
    YOLO(file)(SOURCE, imgsz=32)
