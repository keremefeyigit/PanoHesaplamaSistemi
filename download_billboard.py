from roboflow import Roboflow

# Initialize Roboflow
rf = Roboflow(api_key="your_api_key_here") # You'll need to provide your API key

print("loading billboard dataset...")
# Download the dataset in YOLOv8 format
project = rf.workspace("shaqibs-space").project("billboard-1tlwp")
dataset = project.version(3).download("yolov8")
print(f"Downloaded to {dataset.location}")
