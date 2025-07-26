# from collections import defaultdict
# from copy import deepcopy

# default_callbacks = {
#     'on_start': [lambda: print("Starting...")],
#     'on_end': [lambda: print("Ending...")]
# }

# def get_callbacks():
#     return defaultdict(list, deepcopy(default_callbacks))

# callbacks = get_callbacks()
# print(callbacks)
# for callback in callbacks['on_start']:
#     callback()  

# # 父类 Model
# class Model:
#     def __init__(self, model, task, verbose=True):
#         # 父类的初始化代码
#         print("Initializing parent class Model...")
#         self.model = model
#         self.task = task
#         self.verbose = verbose
#         # 子类实现了，直接调用子类的self.task_map
#         print("Task map: ", self.task_map)  # 调用 task_map，假设父类不知道 task_map 实现

#     @property
#     def task_map(self) -> dict:
#         print("i am father and i have no definition")
#         raise NotImplementedError("Please provide task map for your model!")

# # 子类 YoloModel
# class YoloModel(Model):
#     def __init__(self, model, task, verbose=True):
#         print("Initializing YoloModel subclass...")
#         super().__init__(model=model, task=task, verbose=verbose)

#     @property
#     def task_map(self) -> dict:
#         # 子类实现了 task_map
#         return {
#             "detect": {
#                 "model": "DetectModelClass",
#                 "trainer": "DetectTrainerClass",
#                 "validator": "DetectValidatorClass",
#                 "predictor": "DetectPredictorClass"
#             },
#             "segment": {
#                 "model": "SegmentModelClass",
#                 "trainer": "SegmentTrainerClass",
#                 "validator": "SegmentValidatorClass",
#                 "predictor": "SegmentPredictorClass"
#             }
#         }

# # 实例化子类
# model = YoloModel(model="yolo.pt", task="detect", verbose=True)

# import torch
# import torch.nn as nn

# class MyModel(nn.Module):
#     def __init__(self):
#         super(MyModel, self).__init__()
#         self.conv1 = nn.Conv2d(1, 64, kernel_size=3)
#         self.fc1 = nn.Linear(64, 10)

#     def forward(self, x):
#         x = self.conv1(x)
#         x = torch.relu(x)
#         x = self.fc1(x)
#         return x

# # 创建模型实例
# model = MyModel()

# # 动态添加属性
# model.args = {"batch_size": 32, "learning_rate": 0.001}

# # 访问新添加的属性
# print(model.args)

class A:
    def greet(self):
        print("Hello from A")

class B:
    def greet(self):
        print("Hello from B")

obj = A()  # obj 是 A 类的实例
obj.greet()  # 输出 "Hello from A"

obj.__class__ = B  # 动态修改 obj 的类为 B
obj.greet()  # 输出 "Hello from B"

class MyClass:
    def __init__(self):
        self.a = 1
        self.b = 2

obj = MyClass()
print(obj.__dict__)  # 输出：{'a': 1, 'b': 2}

obj.__dict__['a'] = 3
print(obj.a)  # 输出 3
