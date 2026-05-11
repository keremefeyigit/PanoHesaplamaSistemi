[AKILLI_TABELA_SISTEM_DOKUMANI.md](https://github.com/user-attachments/files/27552872/AKILLI_TABELA_SISTEM_DOKUMANI.md)

# PanoHesaplamaSistemi
Kentsel reklam alanlarının yönetiminde dijital dönüşüm: Belediye ve kamu kurumları için reklam panosu boyutlarını milimetrik hassasiyetle hesaplayan, koordinat takibini otomatize eden OpenCV ve Yapay Zeka destekli yenilikçi analiz ekosistemi.

---

## ⚡ Geliştirici Hızlı Başlangıç

> **Not:** Linux/macOS'ta scriptler `./` prefix'i ile çalıştırılmalıdır.

### 1. İlk Kurulum (tek seferlik)

```bash
chmod +x setup_dev.sh run_tests.sh run_local.sh
./setup_dev.sh --minimal   # hızlı kurulum (test + demo için yeterli)
./setup_dev.sh             # tam kurulum (ultralytics + opencv)
```

### 2. Testleri Çalıştır

```bash
./run_tests.sh             # tüm birim testleri (30 test, hızlı)
./run_tests.sh -k distance # sadece mesafe testleri
```

### 3. Sistemi Localde Çalıştır

```bash
./run_local.sh demo        # formül demo — D=f×B/d, W=W_px×Z/f (donanım yok)
./run_local.sh simulate    # mesafe + GPS simülasyonu tablosu
./run_local.sh yolo        # YOLOv8 ile gerçek tespit dene
./run_local.sh pipeline    # tam pipeline, DB olmadan (50 kare)
./run_local.sh pipeline 200  # 200 kare işle
./run_local.sh             # etkileşimli menü
```

#### Docker ile tam sistem (PostgreSQL + Redis):
```bash
./run_local.sh db-up       # Docker ile PG + Redis başlat
./run_local.sh pipeline-db # pipeline + DB birlikte çalıştır
./run_local.sh db-down     # servisleri durdur
```

---


# Akıllı Tabela Ölçüm ve Tespit Sistemi - Teknik Sistem Dökümanı

## 1. Giriş
Bu döküman, hareket halindeki araçlar (belediye otobüsleri vb.) üzerinden tabelaların (pano) tespiti, boyut ölçümü ve konumlandırılması için geliştirilecek olan "Akıllı Tabela Ölçüm Sistemi"nin teknik gereksinimlerini ve mimari yapısını kapsamaktadır.

---

## 2. Teknik Analiz ve Yaklaşım

### 2.1. OpenCV ve Yapay Zeka (AI) Rol Dağılımı
Sistemde sadece AI (Yolo vb.) kullanımı nesne tespiti için yeterli olsa da, hassas ölçüm ve mesafe tahmini için **Hibrit Yaklaşım** zorunludur.

*   **Yapay Zeka (YOLOv8/v10):** Görüntü akışı içinden "Tabela", "Pano", "Afiş" gibi nesnelerin koordinatlarını (Bounding Box) yüksek hızda tespit eder.
*   **OpenCV:** 
    *   **Kalibrasyon:** Kameraların distorsiyon (bozulma) düzeltmeleri.
    *   **Geometri ve Derinlik:** İki farklı odak uzaklığına sahip kameradan gelen verilerin hizalanması ve benzerlik oranlarının hesaplanması.
    *   **Görüntü İşleme:** Işık dengeleme, kenar belirginleştirme ve perspektif düzeltme.

**Sonuç:** Tespit için AI, matematiksel ölçüm ve derinlik hesabı için OpenCV gereklidir.

### 2.2. Mesafe ve Boyut Ölçümü (Matematiksel Model)
Sistemde geniş açı (Wide-Angle) ve dar açı (Narrow-Angle/Telephoto) olmak üzere iki kamera kullanılacaktır. "Benzer Üçgenler Prensibi" kullanılarak nesnenin gerçek boyutu ve mesafesi hesaplanır.

#### Benzer Üçgenler Formülü:
Bir nesnenin gerçek genişliği ($W$), kameranın odak uzaklığı ($f$), nesnenin kameraya olan uzaklığı ($D$) ve görüntüdeki piksel genişliği ($P$) arasındaki ilişki:
$$D = \frac{W \times f}{P}$$

**Çift Kamera Karşılaştırması:**
Geniş açı kamerada ($P_w, f_w$) ve dar açı kamerada ($P_n, f_n$) aynı nesne tespit edildiğinde:
1.  Odak uzaklığı oranı ($K = f_n / f_w$) sabittir (Kalibrasyon ile belirlenir).
2.  İki görüntü arasındaki piksel farkı ve merkeze olan kayma (Disparity), mesafe ($D$) bilgisini verir.
3.  Mesafe bulunduktan sonra, $W = \frac{D \times P}{f}$ formülü ile tabelanın gerçek boyutları (en/boy) hesaplanır.

---

## 3. Sistem Özellikleri ve Entegrasyon

### 3.1. Harita Entegrasyonu
Tespit edilen her pano, GPS verisi ile eşleştirilerek bir harita (Google Maps, Mapbox veya OpenStreetMap) üzerinde görselleştirilecektir.
*   **Koordinat Eşleme:** Aracın anlık GPS verisi + Kameranın bakış açısı + Hesaplanan mesafe = Tabelanın tam coğrafi konumu.
*   **Katmanlar:** Harita üzerinde tabela türüne göre filtreleme (Dijital, Megalight, Raket vb.).

### 3.2. Veritabanı ve İşleme Hızı
Belediye otobüsü gibi sürekli hareket halindeki araçlarda veri akışı çok hızlıdır (High-Throughput).
*   **Edge Computing:** Görüntü işleme araç üzerinde (NVIDIA Jetson veya benzeri bir NPU üzerinde) yapılmalı, sadece sonuçlar (metadata + küçük resim) sunucuya gönderilmelidir.
*   **Veritabanı Seçimi:** 
    *   **Hızlı Yazma:** Redis (Buffer için) + PostgreSQL (PostGIS eklentisi ile coğrafi veriler için).
    *   **Time-Series:** Verilerin zaman damgalı analizi için InfluxDB tercih edilebilir.

---

## 4. İhtiyaç ve Gider Kalemleri (Genel)

Projenin hayata geçirilmesi için gerekli temel maliyet kalemleri şunlardır:

### 4.1. Donanım Kalemleri
*   **Kamera Ünitesi:** 1 adet Geniş Açı + 1 adet Dar Açı (Yüksek FPS destekli, endüstriyel tip).
*   **İşlem Ünitesi (Edge AI):** GPU/NPU destekli mini bilgisayar (Örn: NVIDIA Jetson Orin).
*   **GPS/GNSS Modülü:** Yüksek hassasiyetli konum belirleme ünitesi.
*   **Bağlantı Ekipmanları:** 4G/5G Modem ve anten seti (Veri transferi için).
*   **Güç Ünitesi:** Araç içi voltaj dalgalanmalarını önleyici regülatör.

### 4.2. Yazılım ve Servis Kalemleri
*   **Harita API Servisleri:** (Google Maps / Mapbox kullanım bazlı maliyetler).
*   **Bulut Sunucu (Cloud):** Verilerin toplanması, işlenmesi ve Dashboard sunumu için.
*   **API Entegrasyonları:** Mevcut belediye sistemleri ile haberleşme katmanı.
*   **Veri Depolama:** Tespit edilen tabela görsellerinin uzun süreli saklanması için Object Storage (S3 vb.).

### 4.3. Operasyonel Kalemler
*   **Veri Hattı (SIM Kart):** Araç başı aylık veri trafiği.
*   **Montaj ve Bakım:** Kameraların kalibrasyonu ve periyodik temizliği.

---

## 5. Sonuç
Önerilen sistem, AI'nın gücünü OpenCV'nin geometrik kesinliği ile birleştirerek, hareket halindeki bir platformdan milimetrik değilse de yüksek doğrulukta tabela envanteri çıkarılmasını sağlar. Harita entegrasyonu ve optimize edilmiş veritabanı yapısı ile belediyecilik hizmetlerinde verimliliği artıracaktır.
