import React, { useEffect, useRef, useState } from 'react';

const defaultInstitutions = [
  { id: 1, slug: 'org-001', name: 'Ankara Büyükşehir Belediyesi' },
  { id: 2, slug: 'org-002', name: 'İstanbul Büyükşehir Belediyesi' }
];

const LiveView = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const resultCanvasRef = useRef<HTMLCanvasElement>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [useUpload, setUseUpload] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  
  const [selectedOrg, setSelectedOrg] = useState('');
  const [organizations, setOrganizations] = useState<{id: any, slug?: string, name: string}[]>(defaultInstitutions);

  const [measurements, setMeasurements] = useState({
    type: '-',
    area: '-',
    distance: '-',
    width: '-',
    height: '-'
  });

  useEffect(() => {
    // Load organizations from local storage or backend if you prefer
    const saved = localStorage.getItem('institutionsData');
    if (saved) {
      const parsed = JSON.parse(saved);
      if(parsed && parsed.length > 0) {
        setOrganizations(parsed);
      }
    }
  }, []);

  useEffect(() => {
    if (useUpload) return;
    async function setupCamera() {
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error("Tarayıcınız kamera API'sini desteklemiyor veya güvenli bağlantı (HTTPS) gerekiyor.");
        }
        const stream = await navigator.mediaDevices.getUserMedia({ 
          video: { facingMode: { ideal: "environment" } } 
        });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.onloadedmetadata = () => {
            videoRef.current?.play().catch(e => console.error("Play error:", e));
          };
          setIsStreaming(true);
        }
      } catch (err: any) {
        console.error("Kamera erişim hatası:", err);
        // HTTP üzerinden erişimde kamera çalışmaz — otomatik olarak fotoğraf yükleme moduna geçiyoruz
        setUseUpload(true);
      }
    }
    setupCamera();

    return () => {
      if (videoRef.current && videoRef.current.srcObject) {
        const tracks = (videoRef.current.srcObject as MediaStream).getTracks();
        tracks.forEach(track => track.stop());
      }
    };
  }, [useUpload]);

  const handleReset = () => {
    setMeasurements({
      type: '-',
      area: '-',
      distance: '-',
      width: '-',
      height: '-'
    });
    setSelectedFile(null);
    setPreviewUrl(null);
  };

  const handleCaptureAndProcess = async () => {
    setIsProcessing(true);
    let blobData: Blob | null = null;

    if (useUpload && selectedFile) {
      blobData = selectedFile;
    } else if (!useUpload && videoRef.current && canvasRef.current) {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        blobData = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg'));
      }
    }

    if (!blobData) {
      alert("Görüntü alınamadı.");
      setIsProcessing(false);
      return;
    }

    // Görüntüyü backend'e gönder
    const formData = new FormData();
    formData.append('file', blobData, 'capture.jpg');
    if (selectedOrg) {
      // Trying to find a slug or pass the string id
      formData.append('org_id', selectedOrg);
    }
    
    // Konum verisi: Gerçek bir uygulamada navigator.geolocation kullanılır
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition((pos) => {
        formData.append('gps_lat', pos.coords.latitude.toString());
        formData.append('gps_lon', pos.coords.longitude.toString());
        sendRequest(formData);
      }, () => {
        sendRequest(formData); // Konum alınamazsa varsayılan
      });
    } else {
      sendRequest(formData);
    }
  };

  const sendRequest = async (formData: FormData) => {
    try {
        const token = localStorage.getItem('token') || 'admin123';
        const API = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
          ? 'http://localhost:8000'
          : window.location.origin;
        const res = await fetch(`${API}/api/detections/process-image`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          },
          body: formData
        });
        
        const data = await res.json();
        if (res.ok) {
            if (data.detection) {
                setMeasurements({
                    type: data.detection.class_label.toUpperCase(),
                    area: `${data.detection.area_m2} m²`,
                    distance: `${data.detection.distance_m} m`,
                    width: `${(data.detection.real_width_m * 100).toFixed(0)} cm`,
                    height: `${(data.detection.real_height_m * 100).toFixed(0)} cm`
                });

                // Canvas'ın render edilmesini bekleyip üstüne çizim yapıyoruz
                setTimeout(() => {
                  drawDetections(data.detection);
                }, 100);

                alert("Ölçüm başarıyla hesaplandı ve sisteme kaydedildi!");
            } else {
                alert("Sunucudan geçerli bir sonuç gelmedi. Tekrar deneyin.");
            }
        } else {
            // API'den gelen hata mesajını kullanıcıya göster
            const errMsg = data?.detail || data?.error || `Sunucu hatası (${res.status})`;
            alert(`Hata: ${errMsg}`);
            console.error("İşleme hatası:", data);
        }
    } catch(e) {
        console.error("API'ye ulaşılamadı", e);
        alert("Sunucuya bağlanılamadı. Backend çalışıyor mu?");
    } finally {
        setIsProcessing(false);
    }
  };

  const drawDetections = (detection: any) => {
    const canvas = resultCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    if (useUpload && previewUrl) {
      const img = new Image();
      img.src = previewUrl;
      img.onload = () => {
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        ctx.drawImage(img, 0, 0);
        renderOverlay(ctx, detection, img.naturalWidth, img.naturalHeight);
      };
    } else if (!useUpload && canvasRef.current) {
      const srcCanvas = canvasRef.current;
      canvas.width = srcCanvas.width;
      canvas.height = srcCanvas.height;
      ctx.drawImage(srcCanvas, 0, 0);
      renderOverlay(ctx, detection, srcCanvas.width, srcCanvas.height);
    }
  };

  const renderOverlay = (ctx: CanvasRenderingContext2D, detection: any, width: number, height: number) => {
    if (!detection || !detection.bbox) return;
    const [x1, y1, x2, y2] = detection.bbox;
    const boxW = x2 - x1;
    const boxH = y2 - y1;

    // 1) Segmentasyon Maskesi (Poligon)
    if (detection.polygon && detection.polygon.length >= 3) {
      ctx.beginPath();
      ctx.moveTo(detection.polygon[0][0], detection.polygon[0][1]);
      for (let i = 1; i < detection.polygon.length; i++) {
        ctx.lineTo(detection.polygon[i][0], detection.polygon[i][1]);
      }
      ctx.closePath();
      ctx.fillStyle = 'rgba(34, 197, 94, 0.25)'; // translucent green
      ctx.fill();
      ctx.strokeStyle = '#22c55e';
      ctx.lineWidth = Math.max(2, Math.round(width / 600));
      ctx.stroke();
    }

    // 2) Bounding Box (Sınır Kutusu)
    ctx.strokeStyle = '#3b82f6'; // vibrant blue
    ctx.lineWidth = Math.max(3, Math.round(width / 400));
    
    // Premium glow efekti
    ctx.shadowColor = 'rgba(59, 130, 246, 0.6)';
    ctx.shadowBlur = 12;
    ctx.strokeRect(x1, y1, boxW, boxH);
    ctx.shadowBlur = 0; // reset shadow

    // Köşe çentikleri
    const tick = Math.max(12, Math.round(boxW * 0.15));
    ctx.strokeStyle = '#60a5fa'; // lighter blue
    ctx.lineWidth = ctx.lineWidth + 2;

    // Top-left
    ctx.beginPath();
    ctx.moveTo(x1 + tick, y1);
    ctx.lineTo(x1, y1);
    ctx.lineTo(x1, y1 + tick);
    ctx.stroke();

    // Top-right
    ctx.beginPath();
    ctx.moveTo(x2 - tick, y1);
    ctx.lineTo(x2, y1);
    ctx.lineTo(x2, y1 + tick);
    ctx.stroke();

    // Bottom-left
    ctx.beginPath();
    ctx.moveTo(x1 + tick, y2);
    ctx.lineTo(x1, y2);
    ctx.lineTo(x1, y2 - tick);
    ctx.stroke();

    // Bottom-right
    ctx.beginPath();
    ctx.moveTo(x2 - tick, y2);
    ctx.lineTo(x2, y2);
    ctx.lineTo(x2, y2 - tick);
    ctx.stroke();

    // 3) Etiket (Label) ve Güven Skoru
    const labelText = `${detection.class_label.toUpperCase()} (${(detection.confidence * 100).toFixed(0)}%)`;
    const fontSize = Math.max(14, Math.round(width / 60));
    ctx.font = `bold ${fontSize}px Inter, -apple-system, sans-serif`;
    const textWidth = ctx.measureText(labelText).width;
    const padding = fontSize * 0.5;

    // Label Arka Planı
    ctx.fillStyle = '#3b82f6';
    const labelY = y1 - fontSize - padding >= 0 ? y1 - fontSize - padding : 0;
    ctx.fillRect(x1, labelY, textWidth + padding * 2, fontSize + padding);

    // Label Yazısı
    ctx.fillStyle = '#ffffff';
    ctx.fillText(labelText, x1 + padding, labelY + fontSize);
  };

  return (
    <div className="live-view-container">
      <div className="card camera-box">
        <div className="camera-header">
          <h3>
            <button 
              className={`toggle-btn ${!useUpload ? 'active' : ''}`}
              onClick={() => { setUseUpload(false); handleReset(); }}
            >Kamera ile İzle</button>
            <button 
              className={`toggle-btn ${useUpload ? 'active' : ''}`}
              onClick={() => { setUseUpload(true); handleReset(); }}
            >Fotoğraf Yükle</button>
          </h3>
          {!useUpload && (
            <span className={`status-badge ${isStreaming ? 'active' : 'inactive'}`}>
              {isStreaming ? 'Aktif' : 'HTTPS Gerekli'}
            </span>
          )}
        </div>
        <div className="video-placeholder">
          {!useUpload && (
            <>
                <video 
                  ref={videoRef} 
                  autoPlay 
                  playsInline 
                  muted 
                  className="live-video"
                  style={{ display: measurements.area !== '-' ? 'none' : 'block' }}
                />
                <canvas ref={canvasRef} style={{ display: 'none' }} />
                
                {!isStreaming && (
                  <div className="loading-overlay" style={{flexDirection: 'column', gap: '0.5rem', textAlign: 'center', padding: '1rem'}}>
                    <span style={{fontSize: '2rem'}}>🔒</span>
                    <span>Kamera için <strong>HTTPS</strong> gerekli.</span>
                    <span style={{fontSize: '0.8rem', opacity: 0.7}}>Fotoğraf Yükle sekmesini kullanabilirsiniz.</span>
                  </div>
                )}
            </>
          )}

          {useUpload && (
            <div className="upload-container" style={{ display: measurements.area !== '-' ? 'none' : 'flex' }}>
               <input 
                 type="file" 
                 accept="image/*" 
                 capture="environment"
                 onChange={(e) => {
                   if (e.target.files && e.target.files[0]) {
                     setSelectedFile(e.target.files[0]);
                     setPreviewUrl(URL.createObjectURL(e.target.files[0]));
                     setMeasurements({ type: '-', area: '-', distance: '-', width: '-', height: '-' });
                   }
                 }}
               />
               {previewUrl && <img src={previewUrl} className="live-video" alt="Preview"/>}
               {!previewUrl && <div className="loading-overlay">Hesaplanacak fotoğrafı seçin</div>}
            </div>
          )}

          {measurements.area !== '-' && (
            <canvas ref={resultCanvasRef} className="live-video" />
          )}

          {measurements.area !== '-' && (
            <div className="overlay-info">
              <div className="measurement-box">
                <p>Tespit: <strong>{measurements.type}</strong></p>
                <p>Alan: <strong>{measurements.area}</strong></p>
              </div>
            </div>
          )}
        </div>
        <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <select 
            value={selectedOrg} 
            onChange={e => setSelectedOrg(e.target.value)}
            style={{ padding: '0.5rem', borderRadius: '4px', flexGrow: 1 }}
            disabled={measurements.area !== '-'}
          >
            <option value="">-- Kurum Seçin (Opsiyonel) --</option>
            {organizations.map(o => (
              <option key={o.id || o.slug} value={o.slug || `org-${o.id}`}>{o.name}</option>
            ))}
          </select>
          {measurements.area !== '-' ? (
            <button 
              className="primary" 
              onClick={handleReset}
            >
              {!useUpload ? "Kamerayı Yeniden Başlat" : "Yeni Fotoğraf Seç"}
            </button>
          ) : (
            <button 
              className="primary" 
              onClick={handleCaptureAndProcess}
              disabled={isProcessing || (!useUpload && !isStreaming) || (useUpload && !selectedFile)}
            >
              {isProcessing ? "Hesaplanıyor..." : "Görüntüyü İşle & Paylaş"}
            </button>
          )}
        </div>
      </div>

      <div className="side-panel">
        <div className="card">
          <h4>Ölçüm Detayları</h4>
          <div className="detail-item">
            <span>En:</span> <strong>{measurements.width}</strong>
          </div>
          <div className="detail-item">
            <span>Boy:</span> <strong>{measurements.height}</strong>
          </div>
          <div className="detail-item">
            <span>Mesafe:</span> <strong>{measurements.distance}</strong>
          </div>
          <div className="detail-item">
            <span>Tip:</span> <strong>{measurements.type}</strong>
          </div>
        </div>
        
        <div className="card" style={{marginTop: '1rem'}}>
          <h4>Sistem Durumu</h4>
          <p style={{fontSize: '0.875rem', color: '#64748b'}}>
            AI Modeli: <span style={{color: '#22c55e'}}>YOLOv8n + Similar Triangles</span><br/>
            Erişim: Web/API Doğrudan
          </p>
        </div>
      </div>

      <style>{`
        .live-view-container {
          display: grid;
          grid-template-columns: 1fr 300px;
          gap: 1.5rem;
        }
        @media (max-width: 900px) {
          .live-view-container {
            grid-template-columns: 1fr;
          }
        }
        .video-placeholder {
          position: relative;
          background: #000;
          border-radius: 0.5rem;
          overflow: hidden;
          aspect-ratio: 16 / 9;
        }
        .live-video {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .upload-container {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100%;
          width: 100%;
          background: #333;
        }
        .upload-container input {
          position: absolute;
          z-index: 10;
          opacity: 0;
          width: 100%;
          height: 100%;
          cursor: pointer;
        }
        .loading-overlay {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          color: white;
          background: #1e293b;
        }
        .overlay-info {
          position: absolute;
          top: 20px;
          left: 20px;
          background: rgba(0,0,0,0.7);
          color: #22c55e;
          padding: 1rem;
          border-left: 4px solid #22c55e;
          border-radius: 4px;
          pointer-events: none;
        }
        .camera-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 1rem;
        }
        .toggle-btn {
          background: none;
          border: none;
          color: #64748b;
          font-size: 1.1rem;
          font-weight: 600;
          cursor: pointer;
          padding-bottom: 0.5rem;
          margin-right: 1.5rem;
        }
        .toggle-btn.active {
          color: #0f172a;
          border-bottom: 2px solid #2563eb;
        }
        .status-badge {
          padding: 0.25rem 0.75rem;
          border-radius: 1rem;
          font-size: 0.875rem;
          height: fit-content;
        }
        .status-badge.active {
          background: #dcfce7;
          color: #166534;
        }
        .status-badge.inactive {
          background: #fee2e2;
          color: #991b1b;
        }
        .detail-item {
          display: flex;
          justify-content: space-between;
          padding: 0.5rem 0;
          border-bottom: 1px solid #f1f5f9;
        }
      `}</style>
    </div>
  );
};

export default LiveView;
