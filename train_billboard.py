from ultralytics import YOLO

# Load the YOLOv8m-seg model
model = YOLO('yolov8m-seg.pt')

print("Starting training on billboard dataset...")
# Train the model
model.train(
    data='billboard-1tlwp-3/data.yaml', # Path will be updated after download
    epochs=100,
    imgsz=640,
    batch=16,
    name='billboard-detector'
)
