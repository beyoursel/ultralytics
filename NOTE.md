# 1. 项目细节记录

## 1.1 pip install -e .
### 作用
1. 开发模式安装：
* 将当前目录中的包以“链接”形式安装到Python环境（而非复制文件）
* 修改链接包的代码无需重新将包安装到环境中，改动会立即生效（因为Python直接引用源码目录）
注意：pyproject.toml会根据设置的项目名，将对应名称的包安装到环境中。
例如在pyroject.toml中定义了下面的ultralytics，就会安装目录下的ultralytics包。
```
[project]
name = "ultralytics"
dynamic = ["version"]
```

2. 自动处理依赖
* 如果当前目录有setup.py或者pyproject.toml文件，pip会解析其中的依赖并自动安装。

注意：
ultralytics项目采用的时pyproject.toml进行相关依赖配置，相较于setup.py更加现代化。

使用命令行pip show ultralytics可以看到下面的内容：
```
Name: ultralytics
Version: 8.3.165
Summary: Ultralytics YOLO 🚀 for SOTA object detection, multi-object tracking, instance segmentation, pose estimation and image classification.
Home-page: https://ultralytics.com
Author: 
Author-email: Glenn Jocher <glenn.jocher@ultralytics.com>, Jing Qiu <jing.qiu@ultralytics.com>
License: AGPL-3.0
Location: /home/taole/anaconda3/envs/ultra/lib/python3.8/site-packages
Editable project location: /media/taole/mydisk/DL_PROJECT/ultralytics
Requires: matplotlib, numpy, opencv-python, pandas, pillow, psutil, py-cpuinfo, pyyaml, requests, scipy, torch, torchvision, tqdm, ultralytics-thop
Required-by: 
```

## 1.2 ultralytics如何实现采用CLI命令yolo执行训练等任务
### 1.2.1 大概的流程
1. 通过pyproject.toml注册命令行入口
ultralytics在包的配置文件pyproject.toml中定义了​​命令行入口点（entry_point）​​，将 yolo命令映射到包内的某个 Python 函数。
通过查找ultralytics下面的pyproject.toml文件，可以发现
```
[project.scripts]
yolo = "ultralytics.cfg:entrypoint"
ultralytics = "ultralytics.cfg:entrypoint"
```
上述定义将yolo和ultralytics映射到包内ultralytics.cfg下面的python函数entrypoint，entrypoint在ultralytics.cfg下的__init__函数中可以找到。
可以在终端中尝试使用ultralytics detect train，和yolo detect train是相同的效果。
2. 运行pip install -e .
* pip会根据pyproject.toml的配置，在系统的可执行路径（如 ~/venv/bin/或 /usr/local/bin/）中生成一个名为 yolo的脚本。由于当前项目是在anaconda虚拟环境中运行的，因此yolo命令可以在～anaconda3/envs/ultra(虚拟环境名)/bin下找到(可以执行which yolo查看路径)
* 该脚本会调用指定的python函数，即ultralytics.cfg:entrypoint。
3. entrypoint函数的实现
* 解析命令行参数
* 根据参数调用对应的功能（如训练、推理、验证等）

## 1.3 ultralytics配置
### 1.3.1 default.yaml
默认使用DEFAULT_CFG_PATH = ROOT / "cfg/default.yaml"下的配置文件。

## 1.4 callback()是怎么触发的
当前项目的callback()貌似都是空的，没有写实际的回调功能

## 1.5 训练相关笔记
### 1.5.1 RANK是什么
在PyTorch分布式训练中：RANK表示当前进程的全局编号（进程rank）；通常，RANK == 0 是主进程，负责日志记录、保存模型、打印信息等；RANK == -1 一般用于非分布式模式，表示当前并未启用分布式训练（如单机单卡）；其他RANK > 0 是从进程。

## 1.6 常用的pytorch方法
### 1.6.1 遍历pytorch模型
```
def _model_train(self):
    """Set model in training mode."""
    self.model.train()
    # Freeze BN stat
    for n, m in self.model.named_modules():
        if any(filter(lambda f: f in n, self.freeze_layer_names)) and isinstance(m, nn.BatchNorm2d):
            m.eval()
```

## 1.7 ultralytics恢复上次训练
```
yolo detect train model=/media/taole/mydisk/DL_PROJECT/ultralytics/runs/detect/train8/weights/last.pt resume=True
# 注意需要指定model=xxx.last.pt，和resume，在default.yaml中设置resume不生效
```

## 1.8 学习率调度器(scheduler)
‵``
def _setup_scheduler(self):
    """Initialize training learning rate scheduler."""
    if self.args.cos_lr:
        self.lf = one_cycle(1, self.args.lrf, self.epochs)  # cosine 1->hyp['lrf']
    else:
        self.lf = lambda x: max(1 - x / self.epochs, 0) * (1.0 - self.args.lrf) + self.args.lrf  # linear 最终学习率与初始学习率的比值
    self.scheduler = optim.lr_scheduler.LambdaLR(self.optimizer, lr_lambda=self.lf)
```
根据输入的epoch计算，当前epoch的学习率与初始学习率的比率，然后可以计算当前epoch需要设置的学习率，一般初始设置0.01，结束时学习率是开始的0.01倍。