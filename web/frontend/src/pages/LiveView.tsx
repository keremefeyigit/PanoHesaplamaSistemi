import React, { useEffect, useRef, useState } from 'react';

const LiveView = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [measurements, setMeasurements] = useState({
    type: 'Billboard',
    area: '12.5 m²',
    distance: '4.2 m',
    width: '350 cm',
    height: '200 cm'
  });

  useEffect(() => {
    async function setupCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
          video: { facingMode: 'environment', width: 1280, height: 720 } 
        });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          setIsStreaming(true);
        }
      } catch (err) {
        console.error("Kamera erişim hatası:", err);
      }
    }
    setupCamera();

    return () => {
      if (videoRef.current && videoRef.current.srcObject) {
        const tracks = (videoRef.current.srcObject as MediaStream).getTracks();
        tracks.forEach(track => track.stop());
      }
    };
  }, []);

  return (
    <div className="live-view-container">
      <div className="card camera-box">
        <div className="camera-header">
          <h3>Canlı Kamera Yayını</h3>
          <span className={`status-badge ${isStreaming ? 'active' : 'inactive'}`}>
            {isStreaming ? 'Aktif' : 'Başlatılıyor...'}
          </span>
        </div>
        <div className="video-placeholder">
          <video 
            ref={videoRef} 
            autoPlay 
            playsInline 
            muted 
            className="live-video"
          />
          {isStreaming && (
            <div className="overlay-info">
              <div className="measurement-box">
                <p>Tespit Edilen Pano: <strong>{measurements.type}</strong></p>
                <p>Hesaplanan Alan: <strong>{measurements.area}</strong></p>
                <p>Mesafe: <strong>{measurements.distance}</strong></p>
              </div>
            </div>
          )}
          {!isStreaming && (
            <div className="loading-overlay">Kamera bağlantısı bekleniyor...</div>
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
          <button className="primary" style={{marginTop: '1rem', width: '100%'}}>Sonucu Kaydet</button>
        </div>
        
        <div className="card" style={{marginTop: '1rem'}}>
          <h4>Sistem Durumu</h4>
          <p style={{fontSize: '0.875rem', color: '#64748b'}}>
            AI Modeli: <span style={{color: '#22c55e'}}>YOLOv8n Loaded</span><br/>
            FPS: 24.5
          </p>
        </div>
      </div>

      <style>{`
        .live-view-container {
          display: grid;
          grid-template-columns: 1fr 300px;
          gap: 1.5rem;
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
        .status-badge {
          padding: 0.25rem 0.75rem;
          border-radius: 1rem;
          font-size: 0.875rem;
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
