from roboflow import Roboflow
import os

def download_datasets(api_key):
    rf = Roboflow(api_key=api_key)
    
    # 1. Koli (Box) Veri Seti - Genel form öğrenimi için
    print("Koli veri seti indiriliyor...")
    box_project = rf.workspace("kerem-efe-yigit").project("boxes-segmentation-2")
    box_dataset = box_project.version(1).download("yolov8")
    
    # 2. Billboard (Pano) Veri Seti - Asıl hedef veri seti
    print("Billboard veri seti indiriliyor...")
    billboard_project = rf.workspace("shaqibs-space").project("billboard-1tlwp")
    billboard_dataset = billboard_project.version(3).download("yolov8")
    
    print(f"Koli veri seti konumu: {box_dataset.location}")
    print(f"Billboard veri seti konumu: {billboard_dataset.location}")

if __name__ == "__main__":
    API_KEY = os.getenv("ROBOFLOW_API_KEY")
    if not API_KEY:
        print("[UYARI] ROBOFLOW_API_KEY ortam değişkeni tanımlı değil. Lütfen export ROBOFLOW_API_KEY='anahtarınız' şeklinde belirtin.")
    else:
        download_datasets(API_KEY)
