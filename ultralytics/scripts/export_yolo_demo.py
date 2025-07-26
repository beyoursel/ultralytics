from ultralytics import YOLO

model = YOLO("/media/taole/mydisk/DL_PROJECT/ultralytics/runs/detect/train8_trained_1e/weights/best.pt")

model.export(format="onnx", dynamic=True, simplify=True)