from ultralytics import YOLO
import os

# Veri seti konfigürasyonu
DATA_PATH = 'training_data/datasets/combined_data/data.yaml'

def train_model():
    # YOLOv8-seg (Segmentasyon) Nano modelini yükle
    # 'yolov8n-seg.pt' pre-trained ağırlıklarıyla başlayıp transfer learning yapacağız.
    model = YOLO('yolov8n-seg.pt')

    # Eğitimi başlat
    model.train(
        data=DATA_PATH,
        epochs=12,             # CPU üzerinde hızlı ve etkili transfer learning için 12 epoch idealdir
        imgsz=640,             # Standart çözünürlük
        batch=16,              # Bellek verimliliği için batch size
        name='billboard_segmentation',
        device='cpu',          # GPU olmadığı için CPU'da çalıştırıyoruz
        
        # ─── GEOMETRİK AUGMENTATIONLARI AKTİFLEŞTİRİYORUZ ───
        # Modelin her uzaklıktan ve açıdan panoları tanımasını sağlamak için kritik öneme sahip
        degrees=10.0,          # Hafif döndürme (yol eğimleri için)
        shear=2.0,             # Hafif bükme
        perspective=0.0005,    # Perspektif varyasyonu (otobüsün panoya yaklaşma açıları için)
        scale=0.5,             # %50 büyük/küçük ölçekleme (YAKINDAKİ BÜYÜK ve uzaktaki küçük panoları yakalamak için CRITICAL!)
        translate=0.1,         # Hafif kaydırma
        flipud=0.0,            # Yukarı-Aşağı çevirme KAPALI (Tabela ters durmaz)
        fliplr=0.5,            # Sol-Sağ çevirme AÇIK (Panoların yolun sağında veya solunda olmasına uyum sağlar)
        mosaic=1.0,            # Mozaik birleştirme AÇIK (Genel nesne çeşitliliği ve arka plan bağlamı için mükemmeldir)
        
        # ─── IŞIK VE HAVA KOŞULLARI AUGMENTATIONLARI AÇIK ───
        hsv_h=0.015,           # Ton
        hsv_s=0.7,             # Doygunluk
        hsv_v=0.4,             # Parlaklık
    )

if __name__ == "__main__":
    train_model()
