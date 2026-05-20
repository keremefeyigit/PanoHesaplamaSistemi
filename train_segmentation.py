from ultralytics import YOLO
import os

# Veri seti konfigürasyonu
DATA_PATH = 'training_data/datasets/combined_data/data.yaml'

def train_model():
    # YOLOv8-seg (Segmentasyon) Nano modelini yükle
    # 'yolov8n-seg.pt' hızlıdır, 'yolov8m-seg.pt' daha doğrudur.
    # Kullanıcının talebi üzerine 'n' (nano) kullanıyoruz.
    model = YOLO('yolov8n-seg.pt')

    # Eğitimi başlat
    model.train(
        data=DATA_PATH,
        epochs=100,            # 100 epoch ideal bir başlangıç
        imgsz=640,             # Standart çözünürlük
        batch=16,              # GPU belleğine göre ayarlanabilir
        name='billboard_segmentation',
        device='cpu',          # GPU varsa '0' yapın
        
        # ─── GEOMETRİK AUGMENTATIONLARI KAPAT ───
        # Tabelanın formunu bozacak işlemleri devre dışı bırakıyoruz
        degrees=0.0,           # Döndürme KAPALI
        shear=0.0,             # Eğme/Bükme KAPALI
        perspective=0.0,       # Perspektif manipülasyonu KAPALI
        scale=0.0,             # Ölçeklendirme KAPALI (Gerçek boyut için kritik)
        translate=0.0,         # Kaydırma KAPALI
        flipud=0.0,            # Yukarı-Aşağı çevirme KAPALI
        fliplr=0.0,            # Sol-Sağ çevirme KAPALI (Tabela metinleri için önemli olabilir)
        mosaic=0.0,            # Mozaik birleştirme KAPALI (Formu bozabilir)
        
        # ─── IŞIK VE HAVA KOŞULLARI AUGMENTATIONLARI AÇIK ───
        # Parlaklık, doygunluk ve kontrast değişimleri
        hsv_h=0.015,           # Ton (Hue)
        hsv_s=0.7,             # Doygunluk (Saturation)
        hsv_v=0.4,             # Parlaklık (Value/Brightness)
        
        # Bulanıklık (Hava koşulları/Kamera sarsıntısı simülasyonu)
        # Not: YOLOv8 default train parametrelerinde 'blur' yoksa bile 
        # augmentasyon kütüphanesi üzerinden (Albumentations) eklenebilir.
        # Standart parametrelerde hsv yeterli bir başlangıçtır.
    )

if __name__ == "__main__":
    train_model()
