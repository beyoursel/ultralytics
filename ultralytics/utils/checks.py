# Ultralytics 🚀 AGPL-3.0 License - https://ultralytics.com/license

import functools
import glob
import inspect
import math
import os
import platform
import re
import shutil
import subprocess
import time
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import cv2
import numpy as np
import torch

from ultralytics.utils import (
    ARM64,
    ASSETS,
    AUTOINSTALL,
    IS_COLAB,
    IS_GIT_DIR,
    IS_JETSON,
    IS_KAGGLE,
    IS_PIP_PACKAGE,
    LINUX,
    LOGGER,
    MACOS,
    ONLINE,
    PYTHON_VERSION,
    RKNN_CHIPS,
    ROOT,
    TORCHVISION_VERSION,
    USER_CONFIG_DIR,
    WINDOWS,
    Retry,
    ThreadingLocked,
    TryExcept,
    clean_url,
    colorstr,
    downloads,
    is_github_action_running,
    url2file,
)


def parse_requirements(file_path=ROOT.parent / "requirements.txt", package=""):
    """
    Parse a requirements.txt file, ignoring lines that start with '#' and any text after '#'.

    Args:
        file_path (Path): Path to the requirements.txt file.
        package (str, optional): Python package to use instead of requirements.txt file.

    Returns:
        requirements (List[SimpleNamespace]): List of parsed requirements as SimpleNamespace objects with `name` and
            `specifier` attributes.

    Examples:
        >>> from ultralytics.utils.checks import parse_requirements
        >>> parse_requirements(package="ultralytics")
    """
    if package:
        requires = [x for x in metadata.distribution(package).requires if "extra == " not in x]
    else:
        requires = Path(file_path).read_text().splitlines()

    requirements = []
    for line in requires:
        line = line.strip()
        if line and not line.startswith("#"):
            line = line.partition("#")[0].strip()  # ignore inline comments
            if match := re.match(r"([a-zA-Z0-9-_]+)\s*([<>!=~]+.*)?", line):
                requirements.append(SimpleNamespace(name=match[1], specifier=match[2].strip() if match[2] else ""))

    return requirements


@functools.lru_cache
def parse_version(version="0.0.0") -> tuple:
    """
    Convert a version string to a tuple of integers, ignoring any extra non-numeric string attached to the version.

    Args:
        version (str): Version string, i.e. '2.0.1+cpu'

    Returns:
        (tuple): Tuple of integers representing the numeric part of the version, i.e. (2, 0, 1)
    """
    try:
        return tuple(map(int, re.findall(r"\d+", version)[:3]))  # '2.0.1+cpu' -> (2, 0, 1)
    except Exception as e:
        LOGGER.warning(f"failure for parse_version({version}), returning (0, 0, 0): {e}")
        return 0, 0, 0


def is_ascii(s) -> bool:
    """
    Check if a string is composed of only ASCII characters.

    Args:
        s (str | list | tuple | dict): Input to be checked (all are converted to string for checking).

    Returns:
        (bool): True if the string is composed only of ASCII characters, False otherwise.
    """
    return all(ord(c) < 128 for c in str(s))


def check_imgsz(imgsz, stride=32, min_dim=1, max_dim=2, floor=0):
    """
    Verify image size is a multiple of the given stride in each dimension. If the image size is not a multiple of the
    stride, update it to the nearest multiple of the stride that is greater than or equal to the given floor value.

    Args:
        imgsz (int | List[int]): Image size.
        stride (int): Stride value.
        min_dim (int): Minimum number of dimensions.
        max_dim (int): Maximum number of dimensions.
        floor (int): Minimum allowed value for image size.

    Returns:
        (List[int] | int): Updated image size.
    """
    # Convert stride to integer if it is a tensor
    stride = int(stride.max() if isinstance(stride, torch.Tensor) else stride)

    # Convert image size to list if it is an integer
    if isinstance(imgsz, int):
        imgsz = [imgsz]
    elif isinstance(imgsz, (list, tuple)):
        imgsz = list(imgsz)
    elif isinstance(imgsz, str):  # i.e. '640' or '[640,640]'
        imgsz = [int(imgsz)] if imgsz.isnumeric() else eval(imgsz)
    else:
        raise TypeError(
            f"'imgsz={imgsz}' is of invalid type {type(imgsz).__name__}. "
            f"Valid imgsz types are int i.e. 'imgsz=640' or list i.e. 'imgsz=[640,640]'"
        )

    # Apply max_dim
    if len(imgsz) > max_dim:
        msg = (
            "'train' and 'val' imgsz must be an integer, while 'predict' and 'export' imgsz may be a [h, w] list "
            "or an integer, i.e. 'yolo export imgsz=640,480' or 'yolo export imgsz=640'"
        )
        if max_dim != 1:
            raise ValueError(f"imgsz={imgsz} is not a valid image size. {msg}")
        LOGGER.warning(f"updating to 'imgsz={max(imgsz)}'. {msg}")
        imgsz = [max(imgsz)]
    # Make image size a multiple of the stride
    sz = [max(math.ceil(x / stride) * stride, floor) for x in imgsz]

    # Print warning message if image size was updated
    if sz != imgsz:
        LOGGER.warning(f"imgsz={imgsz} must be multiple of max stride {stride}, updating to {sz}")

    # Add missing dimensions if necessary
    sz = [sz[0], sz[0]] if min_dim == 2 and len(sz) == 1 else sz[0] if min_dim == 1 and len(sz) == 1 else sz

    return sz


@functools.lru_cache
def check_uv():
    """Check if uv package manager is installed and can run successfully."""
    try:
        return subprocess.run(["uv", "-V"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


@functools.lru_cache
def check_version(
    current: str = "0.0.0",
    required: str = "0.0.0",
    name: str = "version",
    hard: bool = False,
    verbose: bool = False,
    msg: str = "",
) -> bool:
    """
    Check current version against the required version or range.

    Args:
        current (str): Current version or package name to get version from.
        required (str): Required version or range (in pip-style format).
        name (str): Name to be used in warning message.
        hard (bool): If True, raise an AssertionError if the requirement is not met.
        verbose (bool): If True, print warning message if requirement is not met.
        msg (str): Extra message to display if verbose.

    Returns:
        (bool): True if requirement is met, False otherwise.

    Examples:
        Check if current version is exactly 22.04
        >>> check_version(current="22.04", required="==22.04")

        Check if current version is greater than or equal to 22.04
        >>> check_version(current="22.10", required="22.04")  # assumes '>=' inequality if none passed

        Check if current version is less than or equal to 22.04
        >>> check_version(current="22.04", required="<=22.04")

        Check if current version is between 20.04 (inclusive) and 22.04 (exclusive)
        >>> check_version(current="21.10", required=">20.04,<22.04")
    """
    if not current:  # if current is '' or None
        LOGGER.warning(f"invalid check_version({current}, {required}) requested, please check values.")
        return True
    elif not current[0].isdigit():  # current is package name rather than version string, i.e. current='ultralytics'
        try:
            name = current  # assigned package name to 'name' arg
            current = metadata.version(current)  # get version string from package name
        except metadata.PackageNotFoundError as e:
            if hard:
                raise ModuleNotFoundError(f"{current} package is required but not installed") from e
            else:
                return False

    if not required:  # if required is '' or None
        return True

    if "sys_platform" in required and (  # i.e. required='<2.4.0,>=1.8.0; sys_platform == "win32"'
        (WINDOWS and "win32" not in required)
        or (LINUX and "linux" not in required)
        or (MACOS and "macos" not in required and "darwin" not in required)
    ):
        return True

    op = ""
    version = ""
    result = True
    c = parse_version(current)  # '1.2.3' -> (1, 2, 3)
    for r in required.strip(",").split(","):
        op, version = re.match(r"([^0-9]*)([\d.]+)", r).groups()  # split '>=22.04' -> ('>=', '22.04')
        if not op:
            op = ">="  # assume >= if no op passed
        v = parse_version(version)  # '1.2.3' -> (1, 2, 3)
        if op == "==" and c != v:
            result = False
        elif op == "!=" and c == v:
            result = False
        elif op == ">=" and not (c >= v):
            result = False
        elif op == "<=" and not (c <= v):
            result = False
        elif op == ">" and not (c > v):
            result = False
        elif op == "<" and not (c < v):
            result = False
    if not result:
        warning = f"{name}{required} is required, but {name}=={current} is currently installed {msg}"
        if hard:
            raise ModuleNotFoundError(warning)  # assert version requirements met
        if verbose:
            LOGGER.warning(warning)
    return result


def check_latest_pypi_version(package_name="ultralytics"):
    """
    Return the latest version of a PyPI package without downloading or installing it.

    Args:
        package_name (str): The name of the package to find the latest version for.

    Returns:
        (str): The latest version of the package.
    """
    import requests  # slow import

    try:
        requests.packages.urllib3.disable_warnings()  # Disable the InsecureRequestWarning
        response = requests.get(f"https://pypi.org/pypi/{package_name}/json", timeout=3)
        if response.status_code == 200:
            return response.json()["info"]["version"]
    except Exception:
        return None


def check_pip_update_available():
    """
    Check if a new version of the ultralytics package is available on PyPI.

    Returns:
        (bool): True if an update is available, False otherwise.
    """
    if ONLINE and IS_PIP_PACKAGE:
        try:
            from ultralytics import __version__

            latest = check_latest_pypi_version()
            if check_version(__version__, f"<{latest}"):  # check if current version is < latest version
                LOGGER.info(
                    f"New https://pypi.org/project/ultralytics/{latest} available 😃 "
                    f"Update with 'pip install -U ultralytics'"
                )
                return True
        except Exception:
            pass
    return False


@ThreadingLocked()
@functools.lru_cache
def check_font(font="Arial.ttf"):
    """
    Find font locally or download to user's configuration directory if it does not already exist.

    Args:
        font (str): Path or name of font.

    Returns:
        (Path): Resolved font file path.
    """
    from matplotlib import font_manager  # scope for faster 'import ultralytics'

    # Check USER_CONFIG_DIR
    name = Path(font).name
    file = USER_CONFIG_DIR / name
    if file.exists():
        return file

    # Check system fonts
    matches = [s for s in font_manager.findSystemFonts() if font in s]
    if any(matches):
        return matches[0]

    # Download to USER_CONFIG_DIR if missing
    url = f"https://github.com/ultralytics/assets/releases/download/v0.0.0/{name}"
    if downloads.is_url(url, check=True):
        downloads.safe_download(url=url, file=file)
        return file


def check_python(minimum: str = "3.8.0", hard: bool = True, verbose: bool = False) -> bool:
    """
    Check current python version against the required minimum version.

    Args:
        minimum (str): Required minimum version of python.
        hard (bool): If True, raise an AssertionError if the requirement is not met.
        verbose (bool): If True, print warning message if requirement is not met.

    Returns:
        (bool): Whether the installed Python version meets the minimum constraints.
    """
    return check_version(PYTHON_VERSION, minimum, name="Python", hard=hard, verbose=verbose)


@TryExcept()
def check_requirements(requirements=ROOT.parent / "requirements.txt", exclude=(), install=True, cmds=""):
    """
    Check if installed dependencies meet Ultralytics YOLO models requirements and attempt to auto-update if needed.

    Args:
        requirements (Path | str | List[str]): Path to a requirements.txt file, a single package requirement as a
            string, or a list of package requirements as strings.
        exclude (tuple): Tuple of package names to exclude from checking.
        install (bool): If True, attempt to auto-update packages that don't meet requirements.
        cmds (str): Additional commands to pass to the pip install command when auto-updating.

    Examples:
        >>> from ultralytics.utils.checks import check_requirements

        Check a requirements.txt file
        >>> check_requirements("path/to/requirements.txt")

        Check a single package
        >>> check_requirements("ultralytics>=8.0.0")

        Check multiple packages
        >>> check_requirements(["numpy", "ultralytics>=8.0.0"])
    """
    prefix = colorstr("red", "bold", "requirements:")
    if isinstance(requirements, Path):  # requirements.txt file
        file = requirements.resolve()
        assert file.exists(), f"{prefix} {file} not found, check failed."
        requirements = [f"{x.name}{x.specifier}" for x in parse_requirements(file) if x.name not in exclude]
    elif isinstance(requirements, str):
        requirements = [requirements]

    pkgs = []
    for r in requirements:
        r_stripped = r.rpartition("/")[-1].replace(".git", "")  # replace git+https://org/repo.git -> 'repo'
        match = re.match(r"([a-zA-Z0-9-_]+)([<>!=~]+.*)?", r_stripped)
        name, required = match[1], match[2].strip() if match[2] else ""
        try:
            assert check_version(metadata.version(name), required)  # exception if requirements not met
        except (AssertionError, metadata.PackageNotFoundError):
            pkgs.append(r)

    @Retry(times=2, delay=1)
    def attempt_install(packages, commands, use_uv):
        """Attempt package installation with uv if available, falling back to pip."""
        if use_uv:
            base = f"uv pip install --no-cache-dir {packages} {commands} --index-strategy=unsafe-best-match --break-system-packages --prerelease=allow"
            try:
                return subprocess.check_output(base, shell=True, stderr=subprocess.PIPE).decode()
            except subprocess.CalledProcessError as e:
                if e.stderr and "No virtual environment found" in e.stderr.decode():
                    return subprocess.check_output(
                        base.replace("uv pip install", "uv pip install --system"), shell=True
                    ).decode()
                raise
        return subprocess.check_output(f"pip install --no-cache-dir {packages} {commands}", shell=True).decode()

    s = " ".join(f'"{x}"' for x in pkgs)  # console string
    if s:
        if install and AUTOINSTALL:  # check environment variable
            # Note uv fails on arm64 macOS and Raspberry Pi runners
            n = len(pkgs)  # number of packages updates
            LOGGER.info(f"{prefix} Ultralytics requirement{'s' * (n > 1)} {pkgs} not found, attempting AutoUpdate...")
            try:
                t = time.time()
                assert ONLINE, "AutoUpdate skipped (offline)"
                LOGGER.info(attempt_install(s, cmds, use_uv=not ARM64 and check_uv()))
                dt = time.time() - t
                LOGGER.info(f"{prefix} AutoUpdate success ✅ {dt:.1f}s")
                LOGGER.warning(
                    f"{prefix} {colorstr('bold', 'Restart runtime or rerun command for updates to take effect')}\n"
                )
            except Exception as e:
                LOGGER.warning(f"{prefix} ❌ {e}")
                return False
        else:
            return False

    return True


def check_torchvision():
    """
    Check the installed versions of PyTorch and Torchvision to ensure they're compatible.

    This function checks the installed versions of PyTorch and Torchvision, and warns if they're incompatible according
    to the compatibility table based on: https://github.com/pytorch/vision#installation.
    """
    compatibility_table = {
        "2.7": ["0.22"],
        "2.6": ["0.21"],
        "2.5": ["0.20"],
        "2.4": ["0.19"],
        "2.3": ["0.18"],
        "2.2": ["0.17"],
        "2.1": ["0.16"],
        "2.0": ["0.15"],
        "1.13": ["0.14"],
        "1.12": ["0.13"],
    }

    # Check major and minor versions
    v_torch = ".".join(torch.__version__.split("+", 1)[0].split(".")[:2])
    if v_torch in compatibility_table:
        compatible_versions = compatibility_table[v_torch]
        v_torchvision = ".".join(TORCHVISION_VERSION.split("+", 1)[0].split(".")[:2])
        if all(v_torchvision != v for v in compatible_versions):
            LOGGER.warning(
                f"torchvision=={v_torchvision} is incompatible with torch=={v_torch}.\n"
                f"Run 'pip install torchvision=={compatible_versions[0]}' to fix torchvision or "
                "'pip install -U torch torchvision' to update both.\n"
                "For a full compatibility table see https://github.com/pytorch/vision#installation"
            )


def check_suffix(file="yolo11n.pt", suffix=".pt", msg=""):
    """
    Check file(s) for acceptable suffix.

    Args:
        file (str | List[str]): File or list of files to check.
        suffix (str | tuple): Acceptable suffix or tuple of suffixes.
        msg (str): Additional message to display in case of error.
    """
    if file and suffix:
        if isinstance(suffix, str):
            suffix = {suffix}
        for f in file if isinstance(file, (list, tuple)) else [file]:
            if s := str(f).rpartition(".")[-1].lower().strip():  # file suffix
                assert f".{s}" in suffix, f"{msg}{f} acceptable suffix is {suffix}, not .{s}"


def check_yolov5u_filename(file: str, verbose: bool = True):
    """
    Replace legacy YOLOv5 filenames with updated YOLOv5u filenames.

    Args:
        file (str): Filename to check and potentially update.
        verbose (bool): Whether to print information about the replacement.

    Returns:
        (str): Updated filename.
    """
    if "yolov3" in file or "yolov5" in file:
        if "u.yaml" in file:
            file = file.replace("u.yaml", ".yaml")  # i.e. yolov5nu.yaml -> yolov5n.yaml
        elif ".pt" in file and "u" not in file:
            original_file = file
            file = re.sub(r"(.*yolov5([nsmlx]))\.pt", "\\1u.pt", file)  # i.e. yolov5n.pt -> yolov5nu.pt
            file = re.sub(r"(.*yolov5([nsmlx])6)\.pt", "\\1u.pt", file)  # i.e. yolov5n6.pt -> yolov5n6u.pt
            file = re.sub(r"(.*yolov3(|-tiny|-spp))\.pt", "\\1u.pt", file)  # i.e. yolov3-spp.pt -> yolov3-sppu.pt
            if file != original_file and verbose:
                LOGGER.info(
                    f"PRO TIP 💡 Replace 'model={original_file}' with new 'model={file}'.\nYOLOv5 'u' models are "
                    f"trained with https://github.com/ultralytics/ultralytics and feature improved performance vs "
                    f"standard YOLOv5 models trained with https://github.com/ultralytics/yolov5.\n"
                )
    return file


def check_model_file_from_stem(model="yolo11n"):
    """
    Return a model filename from a valid model stem.

    Args:
        model (str): Model stem to check.

    Returns:
        (str | Path): Model filename with appropriate suffix.
    """
    path = Path(model)
    if not path.suffix and path.stem in downloads.GITHUB_ASSETS_STEMS:
        return path.with_suffix(".pt")  # add suffix, i.e. yolo11n -> yolo11n.pt
    return model


def check_file(file, suffix="", download=True, download_dir=".", hard=True):
    """
    Search/download file (if necessary), check suffix (if provided), and return path.

    Args:
        file (str): File name or path.
        suffix (str | tuple): Acceptable suffix or tuple of suffixes to validate against the file.
        download (bool): Whether to download the file if it doesn't exist locally.
        download_dir (str): Directory to download the file to.
        hard (bool): Whether to raise an error if the file is not found.

    Returns:
        (str): Path to the file.
    """
    check_suffix(file, suffix)  # optional
    file = str(file).strip()  # convert to string and strip spaces
    file = check_yolov5u_filename(file)  # yolov5n -> yolov5nu
    if (
        not file
        or ("://" not in file and Path(file).exists())  # '://' check required in Windows Python<3.10
        or file.lower().startswith("grpc://")
    ):  # file exists or gRPC Triton images
        return file
    elif download and file.lower().startswith(("https://", "http://", "rtsp://", "rtmp://", "tcp://")):  # download
        url = file  # warning: Pathlib turns :// -> :/
        file = Path(download_dir) / url2file(file)  # '%2F' to '/', split https://url.com/file.txt?auth
        if file.exists():
            LOGGER.info(f"Found {clean_url(url)} locally at {file}")  # file already exists
        else:
            downloads.safe_download(url=url, file=file, unzip=False)
        return str(file)
    else:  # search
        # 使用glob查找对应的模型或者数据的yaml
        files = glob.glob(str(ROOT / "**" / file), recursive=True) or glob.glob(str(ROOT.parent / file))  # find file
        if not files and hard:
            raise FileNotFoundError(f"'{file}' does not exist")
        elif len(files) > 1 and hard:
            raise FileNotFoundError(f"Multiple files match '{file}', specify exact path: {files}")
        return files[0] if len(files) else []  # return file


def check_yaml(file, suffix=(".yaml", ".yml"), hard=True):
    """
    Search/download YAML file (if necessary) and return path, checking suffix.

    Args:
        file (str | Path): File name or path.
        suffix (tuple): Tuple of acceptable YAML file suffixes.
        hard (bool): Whether to raise an error if the file is not found or multiple files are found.

    Returns:
        (str): Path to the YAML file.
    """
    return check_file(file, suffix, hard=hard)


def check_is_path_safe(basedir, path):
    """
    Check if the resolved path is under the intended directory to prevent path traversal.

    Args:
        basedir (Path | str): The intended directory.
        path (Path | str): The path to check.

    Returns:
        (bool): True if the path is safe, False otherwise.
    """
    base_dir_resolved = Path(basedir).resolve()
    path_resolved = Path(path).resolve()

    return path_resolved.exists() and path_resolved.parts[: len(base_dir_resolved.parts)] == base_dir_resolved.parts


@functools.lru_cache
def check_imshow(warn=False):
    """
    Check if environment supports image displays.

    Args:
        warn (bool): Whether to warn if environment doesn't support image displays.

    Returns:
        (bool): True if environment supports image displays, False otherwise.
    """
    try:
        if LINUX:
            assert not IS_COLAB and not IS_KAGGLE
            assert "DISPLAY" in os.environ, "The DISPLAY environment variable isn't set."
        cv2.imshow("test", np.zeros((8, 8, 3), dtype=np.uint8))  # show a small 8-pixel image
        cv2.waitKey(1)
        cv2.destroyAllWindows()
        cv2.waitKey(1)
        return True
    except Exception as e:
        if warn:
            LOGGER.warning(f"Environment does not support cv2.imshow() or PIL Image.show()\n{e}")
        return False


def check_yolo(verbose=True, device=""):
    """
    Return a human-readable YOLO software and hardware summary.

    Args:
        verbose (bool): Whether to print verbose information.
        device (str | torch.device): Device to use for YOLO.
    """
    import psutil

    from ultralytics.utils.torch_utils import select_device

    if IS_COLAB:
        shutil.rmtree("sample_data", ignore_errors=True)  # remove colab /sample_data directory

    if verbose:
        # System info
        gib = 1 << 30  # bytes per GiB
        ram = psutil.virtual_memory().total
        total, used, free = shutil.disk_usage("/")
        s = f"({os.cpu_count()} CPUs, {ram / gib:.1f} GB RAM, {(total - free) / gib:.1f}/{total / gib:.1f} GB disk)"
        try:
            from IPython import display

            display.clear_output()  # clear display if notebook
        except ImportError:
            pass
    else:
        s = ""

    select_device(device=device, newline=False)
    LOGGER.info(f"Setup complete ✅ {s}")


def collect_system_info():
    """
    Collect and print relevant system information including OS, Python, RAM, CPU, and CUDA.

    Returns:
        (dict): Dictionary containing system information.
    """
    import psutil

    from ultralytics.utils import ENVIRONMENT  # scope to avoid circular import
    from ultralytics.utils.torch_utils import get_cpu_info, get_gpu_info

    gib = 1 << 30  # bytes per GiB
    cuda = torch.cuda.is_available()
    check_yolo()
    total, used, free = shutil.disk_usage("/")

    info_dict = {
        "OS": platform.platform(),
        "Environment": ENVIRONMENT,
        "Python": PYTHON_VERSION,
        "Install": "git" if IS_GIT_DIR else "pip" if IS_PIP_PACKAGE else "other",
        "Path": str(ROOT),
        "RAM": f"{psutil.virtual_memory().total / gib:.2f} GB",
        "Disk": f"{(total - free) / gib:.1f}/{total / gib:.1f} GB",
        "CPU": get_cpu_info(),
        "CPU count": os.cpu_count(),
        "GPU": get_gpu_info(index=0) if cuda else None,
        "GPU count": torch.cuda.device_count() if cuda else None,
        "CUDA": torch.version.cuda if cuda else None,
    }
    LOGGER.info("\n" + "\n".join(f"{k:<20}{v}" for k, v in info_dict.items()) + "\n")

    package_info = {}
    for r in parse_requirements(package="ultralytics"):
        try:
            current = metadata.version(r.name)
            is_met = "✅ " if check_version(current, str(r.specifier), name=r.name, hard=True) else "❌ "
        except metadata.PackageNotFoundError:
            current = "(not installed)"
            is_met = "❌ "
        package_info[r.name] = f"{is_met}{current}{r.specifier}"
        LOGGER.info(f"{r.name:<20}{package_info[r.name]}")

    info_dict["Package Info"] = package_info

    if is_github_action_running():
        github_info = {
            "RUNNER_OS": os.getenv("RUNNER_OS"),
            "GITHUB_EVENT_NAME": os.getenv("GITHUB_EVENT_NAME"),
            "GITHUB_WORKFLOW": os.getenv("GITHUB_WORKFLOW"),
            "GITHUB_ACTOR": os.getenv("GITHUB_ACTOR"),
            "GITHUB_REPOSITORY": os.getenv("GITHUB_REPOSITORY"),
            "GITHUB_REPOSITORY_OWNER": os.getenv("GITHUB_REPOSITORY_OWNER"),
        }
        LOGGER.info("\n" + "\n".join(f"{k}: {v}" for k, v in github_info.items()))
        info_dict["GitHub Info"] = github_info

    return info_dict


def check_amp(model):
    """
    Check the PyTorch Automatic Mixed Precision (AMP) functionality of a YOLO model.

    If the checks fail, it means there are anomalies with AMP on the system that may cause NaN losses or zero-mAP
    results, so AMP will be disabled during training.

    Args:
        model (torch.nn.Module): A YOLO model instance.

    Returns:
        (bool): Returns True if the AMP functionality works correctly with YOLO11 model, else False.

    Examples:
        >>> from ultralytics import YOLO
        >>> from ultralytics.utils.checks import check_amp
        >>> model = YOLO("yolo11n.pt").model.cuda()
        >>> check_amp(model)
    """
    from ultralytics.utils.torch_utils import autocast

    device = next(model.parameters()).device  # get model device
    prefix = colorstr("AMP: ")
    if device.type in {"cpu", "mps"}:
        return False  # AMP only used on CUDA devices
    else:
        # GPUs that have issues with AMP
        pattern = re.compile(
            r"(nvidia|geforce|quadro|tesla).*?(1660|1650|1630|t400|t550|t600|t1000|t1200|t2000|k40m)", re.IGNORECASE
        )

        gpu = torch.cuda.get_device_name(device)
        if bool(pattern.search(gpu)):
            LOGGER.warning(
                f"{prefix}checks failed ❌. AMP training on {gpu} GPU may cause "
                f"NaN losses or zero-mAP results, so AMP will be disabled during training."
            )
            return False

    def amp_allclose(m, im):
        """All close FP32 vs AMP results."""
        """
        全精度 FP32 和 混合精度 AMP（Automatic Mixed Precision） 
        下模型推理结果的一致性，用于验证模型在开启 AMP 的情况下是否还能保持合理精度。
        """
        batch = [im] * 8
        imgsz = max(256, int(model.stride.max() * 4))  # max stride P5-32 and P6-64
        a = m(batch, imgsz=imgsz, device=device, verbose=False)[0].boxes.data  # FP32 inference
        with autocast(enabled=True): # 混合精度前向传播
            b = m(batch, imgsz=imgsz, device=device, verbose=False)[0].boxes.data  # AMP inference
        del m
        return a.shape == b.shape and torch.allclose(a, b.float(), atol=0.5)  # close to 0.5 absolute tolerance

    im = ASSETS / "bus.jpg"  # image to check
    LOGGER.info(f"{prefix}running Automatic Mixed Precision (AMP) checks...")
    warning_msg = "Setting 'amp=True'. If you experience zero-mAP or NaN losses you can disable AMP with amp=False."
    try:
        from ultralytics import YOLO

        assert amp_allclose(YOLO("yolo11n.pt"), im)
        LOGGER.info(f"{prefix}checks passed ✅")
    except ConnectionError:
        LOGGER.warning(f"{prefix}checks skipped. Offline and unable to download YOLO11n for AMP checks. {warning_msg}")
    except (AttributeError, ModuleNotFoundError):
        LOGGER.warning(
            f"{prefix}checks skipped. "
            f"Unable to load YOLO11n for AMP checks due to possible Ultralytics package modifications. {warning_msg}"
        )
    except AssertionError:
        LOGGER.error(
            f"{prefix}checks failed. Anomalies were detected with AMP on your system that may lead to "
            f"NaN losses or zero-mAP results, so AMP will be disabled during training."
        )
        return False
    return True


def git_describe(path=ROOT):  # path must be a directory
    """
    Return human-readable git description, i.e. v5.0-5-g3e25f1e https://git-scm.com/docs/git-describe.

    Args:
        path (Path): Path to git repository.

    Returns:
        (str): Human-readable git description.
    """
    try:
        return subprocess.check_output(f"git -C {path} describe --tags --long --always", shell=True).decode()[:-1]
    except Exception:
        return ""


def print_args(args: Optional[dict] = None, show_file=True, show_func=False):
    """
    Print function arguments (optional args dict).

    Args:
        args (dict, optional): Arguments to print.
        show_file (bool): Whether to show the file name.
        show_func (bool): Whether to show the function name.
    """

    def strip_auth(v):
        """Clean longer Ultralytics HUB URLs by stripping potential authentication information."""
        return clean_url(v) if (isinstance(v, str) and v.startswith("http") and len(v) > 100) else v

    x = inspect.currentframe().f_back  # previous frame
    file, _, func, _, _ = inspect.getframeinfo(x)
    if args is None:  # get args automatically
        args, _, _, frm = inspect.getargvalues(x)
        args = {k: v for k, v in frm.items() if k in args}
    try:
        file = Path(file).resolve().relative_to(ROOT).with_suffix("")
    except ValueError:
        file = Path(file).stem
    s = (f"{file}: " if show_file else "") + (f"{func}: " if show_func else "")
    LOGGER.info(colorstr(s) + ", ".join(f"{k}={strip_auth(v)}" for k, v in sorted(args.items())))


def cuda_device_count() -> int:
    """
    Get the number of NVIDIA GPUs available in the environment.

    Returns:
        (int): The number of NVIDIA GPUs available.
    """
    if IS_JETSON:
        # NVIDIA Jetson does not fully support nvidia-smi and therefore use PyTorch instead
        return torch.cuda.device_count()
    else:
        try:
            # Run the nvidia-smi command and capture its output
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=count", "--format=csv,noheader,nounits"], encoding="utf-8"
            )

            # Take the first line and strip any leading/trailing white space
            first_line = output.strip().split("\n", 1)[0]

            return int(first_line)
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
            # If the command fails, nvidia-smi is not found, or output is not an integer, assume no GPUs are available
            return 0


def cuda_is_available() -> bool:
    """
    Check if CUDA is available in the environment.

    Returns:
        (bool): True if one or more NVIDIA GPUs are available, False otherwise.
    """
    return cuda_device_count() > 0


def is_rockchip():
    """
    Check if the current environment is running on a Rockchip SoC.

    Returns:
        (bool): True if running on a Rockchip SoC, False otherwise.
    """
    if LINUX and ARM64:
        try:
            with open("/proc/device-tree/compatible") as f:
                dev_str = f.read()
                *_, soc = dev_str.split(",")
                if soc.replace("\x00", "") in RKNN_CHIPS:
                    return True
        except OSError:
            return False
    else:
        return False


def is_intel():
    """
    Check if the system has Intel hardware (CPU or GPU).

    Returns:
        (bool): True if Intel hardware is detected, False otherwise.
    """
    from ultralytics.utils.torch_utils import get_cpu_info

    # Check CPU
    if "intel" in get_cpu_info().lower():
        return True

    # Check GPU via xpu-smi
    try:
        result = subprocess.run(["xpu-smi", "discovery"], capture_output=True, text=True, timeout=5)
        return "intel" in result.stdout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False


def is_sudo_available() -> bool:
    """
    Check if the sudo command is available in the environment.

    Returns:
        (bool): True if the sudo command is available, False otherwise.
    """
    if WINDOWS:
        return False
    cmd = "sudo --version"
    return subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


# Run checks and define constants
check_python("3.8", hard=False, verbose=True)  # check python version
check_torchvision()  # check torch-torchvision compatibility

# Define constants
IS_PYTHON_3_8 = PYTHON_VERSION.startswith("3.8")
IS_PYTHON_3_12 = PYTHON_VERSION.startswith("3.12")
IS_PYTHON_3_13 = PYTHON_VERSION.startswith("3.13")

IS_PYTHON_MINIMUM_3_10 = check_python("3.10", hard=False)
IS_PYTHON_MINIMUM_3_12 = check_python("3.12", hard=False)
