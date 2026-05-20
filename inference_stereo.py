import cv2
import numpy as np
from ultralytics import YOLO
from config import config # config.py'den kamera sabitlerini alıyoruz

class BillboardMeasurer:
    def __init__(self, model_path='models/best.pt'):
        # Eğitilen YOLOv8-seg modelini yükle
        self.model = YOLO(model_path)
        
        # Kamera parametrelerini config'den al
        self.focal_length = config.cameras.wide.focal_length_px
        self.cx = config.cameras.wide.cx
        self.cy = config.cameras.wide.cy
        
    def get_mask_and_polygons(self, image):
        """YOLOv8-seg ile tespit yap ve maske/poligonları döndür."""
        results = self.model(image)[0]
        
        detections = []
        if results.masks is not None:
            for mask, poly, cls in zip(results.masks.data, results.masks.xy, results.boxes.cls):
                # Sadece 'billboard' sınıfını al (Eğer class 1 ise)
                if int(cls) == 1: 
                    binary_mask = mask.cpu().numpy().astype(np.uint8)
                    detections.append({
                        'mask': binary_mask,
                        'polygon': poly, # Piksel koordinatları
                    })
        return detections

    def calculate_real_dimensions(self, polygon, depth_map):
        """
        Derinlik (Z) ve Poligon kullanarak gerçek dünya boyutlarını hesaplar.
        3D Re-projection yaklaşımı.
        """
        # 1. Tabela üzerindeki derinlik piksellerini topla
        # Poligon içindeki pikselleri maskele
        mask = np.zeros(depth_map.shape, dtype=np.uint8)
        cv2.fillPoly(mask, [polygon.astype(np.int32)], 1)
        
        # 2. Maskelenen bölgedeki derinlik değerlerinin medyanını al
        # (Gürültüden arındırmak için medyan tercih edilir)
        tabela_depths = depth_map[mask == 1]
        if len(tabela_depths) == 0:
            return None
        
        # 0 veya geçersiz derinlikleri temizle
        tabela_depths = tabela_depths[tabela_depths > 0]
        if len(tabela_depths) == 0:
            return None
            
        Z_median = np.median(tabela_depths)
        
        # 3. Poligon köşelerini 3D koordinatlara (X, Y, Z) çevir
        # X = (x - cx) * Z / f
        # Y = (y - cy) * Z / f
        points_3d = []
        for (x, y) in polygon:
            X = (x - self.cx) * Z_median / self.focal_length
            Y = (y - self.cy) * Z_median / self.focal_length
            points_3d.append([X, Y, Z_median])
        
        points_3d = np.array(points_3d)
        
        # 4. Alan Hesabı (3D Poligon Alanı)
        # Basitleştirilmiş: Eğer Z yaklaşık sabitse, 2D Shoelace formülü (X, Y) kullanılabilir
        area = self._polygon_area_3d(points_3d)
        
        # 5. En-Boy Hesabı (Bounding Box yaklaşımı ile 3D düzlemde)
        # 3D noktaların min/max farkı kabaca en/boy verir (açılı duruşlar için daha karmaşık hesap gerekebilir)
        width = np.max(points_3d[:, 0]) - np.min(points_3d[:, 0])
        height = np.max(points_3d[:, 1]) - np.min(points_3d[:, 1])
        
        return {
            'distance_m': Z_median,
            'area_m2': area,
            'width_m': width,
            'height_m': height
        }

    def _polygon_area_3d(self, points):
        """3D koordinatlardaki poligonun alanını hesaplar."""
        # 3D poligon alanı için genel formül (Cross product toplamı)
        if len(points) < 3: return 0
        area = np.zeros(3)
        for i in range(len(points)):
            p1 = points[i]
            p2 = points[(i + 1) % len(points)]
            area += np.cross(p1, p2)
        return 0.5 * np.linalg.norm(area)

def process_frame(frame, disparity_map):
    """Ana işlem döngüsü örneği."""
    # 1. Disparity Map'i Metre cinsinden Derinliğe (Z) çevir
    # Z = (f * baseline) / disparity
    baseline = config.cameras.baseline_m
    f = config.cameras.wide.focal_length_px
    
    # 0'a bölme hatasını engelle
    disparity_map[disparity_map <= 0] = 0.1
    depth_map = (f * baseline) / disparity_map
    
    # 2. Ölçüm sınıfını başlat
    measurer = BillboardMeasurer(model_path='models/billboard_segmentation/weights/best.pt')
    
    # 3. Tespitleri yap
    detections = measurer.get_mask_and_polygons(frame)
    
    for det in detections:
        results = measurer.calculate_real_dimensions(det['polygon'], depth_map)
        
        if results:
            print(f"--- Tabela Tespit Edildi ---")
            print(f"Mesafe: {results['distance_m']:.2f} m")
            print(f"Alan: {results['area_m2']:.2f} m2")
            print(f"Boyutlar: {results['width_m']:.2f}m x {results['height_m']:.2f}m")
            
            # Görselleştirme
            cv2.polylines(frame, [det['polygon'].astype(np.int32)], True, (0, 255, 0), 2)
            cv2.putText(frame, f"{results['area_m2']:.2f} m2", 
                        tuple(det['polygon'][0].astype(int)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    return frame

if __name__ == "__main__":
    # Örnek kullanım (Kodun yapısını göstermek içindir)
    print("Stereo Entegrasyon Modülü Hazır.")
    # frame = cv2.imread('test.jpg')
    # disp = cv2.imread('disparity.png', 0)
    # output = process_frame(frame, disp)
    # cv2.imshow('Result', output)
    # cv2.waitKey(0)
