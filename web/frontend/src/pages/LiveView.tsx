import React, { useEffect, useRef, useState } from 'react';

const defaultInstitutions = [
  { id: 1, slug: 'org-001', name: 'Ankara Büyükşehir Belediyesi' },
  { id: 2, slug: 'org-002', name: 'İstanbul Büyükşehir Belediyesi' }
];

const LiveView = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
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
          video: { facingMode: "environment" } 
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
        alert(`Kameraya erişilemedi: ${err.message}. Lütfen HTTPS kullanın veya tarayıcı izinlerini kontrol edin.`);
        setUseUpload(true); // Fallback to upload if camera fails
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
        const res = await fetch('http://localhost:8000/api/detections/process-image', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          },
          body: formData
        });
        
        if (res.ok) {
            const data = await res.json();
            if (data.detection) {
                setMeasurements({
                    type: data.detection.class_label.toUpperCase(),
                    area: `${data.detection.area_m2} m²`,
                    distance: `${data.detection.distance_m} m`,
                    width: `${(data.detection.real_width_m * 100).toFixed(0)} cm`,
                    height: `${(data.detection.real_height_m * 100).toFixed(0)} cm`
                });
                alert("Ölçüm başarıyla hesaplandı ve sisteme kaydedildi/paylaşıldı.");
            }
        } else {
            console.error("İşleme hatası");
        }
    } catch(e) {
        console.error("API'ye ulaşılamadı", e);
    } finally {
        setIsProcessing(false);
    }
  };

  return (
    <div className="live-view-container">
      <div className="card camera-box">
        <div className="camera-header">
          <h3>
            <button 
              className={`toggle-btn ${!useUpload ? 'active' : ''}`}
              onClick={() => setUseUpload(false)}
            >Kamera ile İzle</button>
            <button 
              className={`toggle-btn ${useUpload ? 'active' : ''}`}
              onClick={() => setUseUpload(true)}
            >Fotoğraf Yükle</button>
          </h3>
          {!useUpload && (
            <span className={`status-badge ${isStreaming ? 'active' : 'inactive'}`}>
              {isStreaming ? 'Aktif' : 'Başlatılıyor...'}
            </span>
          )}
        </div>
        <div className="video-placeholder">
          {!useUpload ? (
            <>
                <video 
                  ref={videoRef} 
                  autoPlay 
                  playsInline 
                  muted 
                  className="live-video"
                />
                <canvas ref={canvasRef} style={{ display: 'none' }} />
                
                {isStreaming && measurements.area !== '-' && (
                  <div className="overlay-info">
                    <div className="measurement-box">
                      <p>Tespit: <strong>{measurements.type}</strong></p>
                      <p>Alan: <strong>{measurements.area}</strong></p>
                    </div>
                  </div>
                )}
                {!isStreaming && (
                  <div className="loading-overlay">Kamera bağlantısı bekleniyor... Veya bilgisayar kameranıza izin verin.</div>
                )}
            </>
          ) : (
            <div className="upload-container">
               <input 
                 type="file" 
                 accept="image/*" 
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
        </div>
        <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <select 
            value={selectedOrg} 
            onChange={e => setSelectedOrg(e.target.value)}
            style={{ padding: '0.5rem', borderRadius: '4px', flexGrow: 1 }}
          >
            <option value="">-- Kurum Seçin (Opsiyonel) --</option>
            {organizations.map(o => (
              <option key={o.id || o.slug} value={o.slug || `org-${o.id}`}>{o.name}</option>
            ))}
          </select>
          <button 
            className="primary" 
            onClick={handleCaptureAndProcess}
            disabled={isProcessing || (!useUpload && !isStreaming) || (useUpload && !selectedFile)}
          >
            {isProcessing ? "Hesaplanıyor..." : "Görüntüyü İşle & Paylaş"}
          </button>
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
