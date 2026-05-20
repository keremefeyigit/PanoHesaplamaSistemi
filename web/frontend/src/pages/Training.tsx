import React, { useState, useRef, useCallback, useEffect } from 'react';

const API = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000'
  : window.location.origin;

interface ImageInfo {
  filename: string;
  size_kb: number;
  uploaded_at: number;
}

interface TrainingStatus {
  state: 'idle' | 'running' | 'done' | 'error';
  started_at: number | null;
  finished_at: number | null;
  image_count: number;
  log_lines: string[];
  model_ready: boolean;
  error: string | null;
  total_images: number;
}

export default function Training() {
  const [images, setImages] = useState<ImageInfo[]>([]);
  const [status, setStatus] = useState<TrainingStatus | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [epochs, setEpochs] = useState(50);
  const [selectedPreview, setSelectedPreview] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<{ [key: string]: number }>({});
  const fileInputRef = useRef<HTMLInputElement>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const fetchImages = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/training/images`);
      const data = await res.json();
      setImages(data.images || []);
    } catch {}
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/training/status`);
      const data = await res.json();
      setStatus(data);
    } catch {}
  }, []);

  useEffect(() => {
    fetchImages();
    fetchStatus();
  }, [fetchImages, fetchStatus]);

  // Eğitim sırasında log'u her 3 saniyede yenile
  useEffect(() => {
    if (status?.state === 'running') {
      const interval = setInterval(() => {
        fetchStatus();
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [status?.state, fetchStatus]);

  // Log alanını en alta kaydır
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [status?.log_lines]);

  const uploadFiles = async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    setUploading(true);
    let successCount = 0;

    for (const file of fileArray) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        setUploadProgress(prev => ({ ...prev, [file.name]: 0 }));
        const res = await fetch(`${API}/api/training/upload`, {
          method: 'POST',
          body: formData,
        });
        const data = await res.json();
        if (res.ok) {
          successCount++;
          setUploadProgress(prev => ({ ...prev, [file.name]: 100 }));
        } else {
          alert(`${file.name}: ${data.detail}`);
        }
      } catch {
        alert(`${file.name} yüklenirken hata oluştu.`);
      }
    }

    setUploading(false);
    setUploadProgress({});
    if (successCount > 0) {
      await fetchImages();
      await fetchStatus();
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) uploadFiles(e.target.files);
    e.target.value = '';
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files) uploadFiles(e.dataTransfer.files);
  };

  const handleDelete = async (filename: string) => {
    if (!confirm(`"${filename}" silinsin mi?`)) return;
    await fetch(`${API}/api/training/images/${filename}`, { method: 'DELETE' });
    setImages(prev => prev.filter(img => img.filename !== filename));
    await fetchStatus();
  };

  const startTraining = async () => {
    if (!confirm(`${images.length} fotoğraf ile ${epochs} epoch eğitim başlatılsın mı? Bu işlem uzun sürebilir.`)) return;
    const form = new FormData();
    form.append('epochs', String(epochs));
    const res = await fetch(`${API}/api/training/start`, { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) { alert(data.detail); return; }
    alert(data.message);
    fetchStatus();
  };

  const formatDate = (ts: number) =>
    new Date(ts * 1000).toLocaleString('tr-TR');

  const statusColor = {
    idle: '#94a3b8',
    running: '#f59e0b',
    done: '#22c55e',
    error: '#ef4444',
  };

  const statusText = {
    idle: 'Hazır',
    running: '⏳ Eğitim Devam Ediyor...',
    done: '✅ Eğitim Tamamlandı',
    error: '❌ Hata',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>

      {/* Başlık Kartı */}
      <div style={{
        background: 'linear-gradient(135deg, #1e3a5f 0%, #0f2340 100%)',
        borderRadius: '16px',
        padding: '28px 32px',
        border: '1px solid rgba(99,179,237,0.2)',
        boxShadow: '0 4px 24px rgba(0,0,0,0.3)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{
            width: '52px', height: '52px', borderRadius: '14px',
            background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '24px', boxShadow: '0 4px 12px rgba(59,130,246,0.4)',
          }}>🧠</div>
          <div>
            <h2 style={{ margin: 0, color: '#e2e8f0', fontSize: '22px', fontWeight: 700 }}>
              YOLO Model Eğitimi
            </h2>
            <p style={{ margin: '4px 0 0', color: '#94a3b8', fontSize: '14px' }}>
              Pano fotoğrafı yükleyin → Modeli eğitin → Sistem otomatik tanısın
            </p>
          </div>
          {status && (
            <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: '8px',
                background: 'rgba(0,0,0,0.3)', borderRadius: '20px',
                padding: '6px 16px', border: `1px solid ${statusColor[status.state]}40`,
              }}>
                <div style={{
                  width: '8px', height: '8px', borderRadius: '50%',
                  background: statusColor[status.state],
                  boxShadow: status.state === 'running' ? `0 0 8px ${statusColor[status.state]}` : 'none',
                  animation: status.state === 'running' ? 'pulse 1.5s infinite' : 'none',
                }} />
                <span style={{ color: statusColor[status.state], fontSize: '13px', fontWeight: 600 }}>
                  {statusText[status.state]}
                </span>
              </div>
              {status.model_ready && (
                <div style={{ color: '#22c55e', fontSize: '12px', marginTop: '6px' }}>
                  ✓ Model aktif: yolov8n_tabela.pt
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>

        {/* SOL: Fotoğraf Yükleme Alanı */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${dragOver ? '#3b82f6' : 'rgba(99,179,237,0.3)'}`,
              borderRadius: '16px',
              padding: '40px 24px',
              textAlign: 'center',
              cursor: 'pointer',
              background: dragOver
                ? 'rgba(59,130,246,0.1)'
                : 'rgba(255,255,255,0.03)',
              transition: 'all 0.2s',
              position: 'relative',
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/jpeg,image/png,image/webp,image/bmp"
              onChange={handleFileInput}
              style={{ display: 'none' }}
            />
            <div style={{ fontSize: '48px', marginBottom: '12px' }}>📸</div>
            <div style={{ color: '#e2e8f0', fontWeight: 600, fontSize: '16px', marginBottom: '8px' }}>
              Pano Fotoğraflarını Sürükle & Bırak
            </div>
            <div style={{ color: '#64748b', fontSize: '13px', marginBottom: '16px' }}>
              veya tıklayarak dosya seç
            </div>
            <div style={{
              display: 'inline-block',
              background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
              color: 'white', borderRadius: '8px', padding: '10px 24px',
              fontSize: '14px', fontWeight: 600,
            }}>
              {uploading ? '⏳ Yükleniyor...' : '+ Fotoğraf Seç'}
            </div>
            <div style={{ color: '#475569', fontSize: '11px', marginTop: '12px' }}>
              JPG, PNG, WEBP — Maks. 20 MB — Çoklu seçim desteklenir
            </div>
          </div>

          {/* Yükleme ilerleme */}
          {Object.keys(uploadProgress).length > 0 && (
            <div style={{
              background: 'rgba(255,255,255,0.05)', borderRadius: '12px', padding: '16px',
              border: '1px solid rgba(255,255,255,0.08)',
            }}>
              {Object.entries(uploadProgress).map(([name, pct]) => (
                <div key={name} style={{ marginBottom: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span style={{ color: '#94a3b8', fontSize: '12px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '200px' }}>{name}</span>
                    <span style={{ color: '#3b82f6', fontSize: '12px' }}>{pct}%</span>
                  </div>
                  <div style={{ height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px' }}>
                    <div style={{ height: '100%', width: `${pct}%`, background: '#3b82f6', borderRadius: '2px', transition: 'width 0.3s' }} />
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Eğitim Başlatma */}
          <div style={{
            background: 'rgba(255,255,255,0.04)', borderRadius: '16px', padding: '20px',
            border: '1px solid rgba(255,255,255,0.08)',
          }}>
            <h3 style={{ margin: '0 0 16px', color: '#e2e8f0', fontSize: '15px' }}>⚙️ Eğitim Ayarları</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <label style={{ color: '#94a3b8', fontSize: '13px', whiteSpace: 'nowrap' }}>Epoch Sayısı:</label>
              <input
                type="number"
                value={epochs}
                onChange={e => setEpochs(Number(e.target.value))}
                min={10} max={300}
                style={{
                  background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: '8px', padding: '8px 12px', color: '#e2e8f0',
                  width: '80px', fontSize: '14px',
                }}
              />
              <span style={{ color: '#475569', fontSize: '12px' }}>(10–300)</span>
            </div>
            <div style={{ color: '#64748b', fontSize: '12px', marginBottom: '16px', lineHeight: 1.6 }}>
              📌 <b style={{ color: '#94a3b8' }}>Öneri:</b> 10–30 fotoğraf için 50 epoch yeterli.<br/>
              50+ fotoğraf için 100 epoch deneyin. CPU'da ~5–30 dk sürer.
            </div>
            <button
              onClick={startTraining}
              disabled={!images.length || status?.state === 'running'}
              style={{
                width: '100%',
                background: images.length && status?.state !== 'running'
                  ? 'linear-gradient(135deg, #22c55e, #16a34a)'
                  : 'rgba(255,255,255,0.08)',
                border: 'none', borderRadius: '10px',
                color: images.length && status?.state !== 'running' ? 'white' : '#475569',
                padding: '12px', fontSize: '15px', fontWeight: 700,
                cursor: images.length && status?.state !== 'running' ? 'pointer' : 'not-allowed',
                transition: 'all 0.2s',
              }}
            >
              {status?.state === 'running' ? '⏳ Eğitim Sürüyor...' : `🚀 Eğitimi Başlat (${images.length} fotoğraf)`}
            </button>
          </div>
        </div>

        {/* SAĞ: Fotoğraf Galerisi */}
        <div style={{
          background: 'rgba(255,255,255,0.03)', borderRadius: '16px', padding: '20px',
          border: '1px solid rgba(255,255,255,0.08)',
          maxHeight: '500px', overflowY: 'auto',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: 0, color: '#e2e8f0', fontSize: '15px' }}>
              🖼️ Yüklenen Fotoğraflar
            </h3>
            <span style={{
              background: 'rgba(59,130,246,0.2)', color: '#60a5fa',
              borderRadius: '20px', padding: '2px 12px', fontSize: '12px',
            }}>
              {images.length} adet
            </span>
          </div>

          {images.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: '#475569' }}>
              <div style={{ fontSize: '40px', marginBottom: '12px' }}>📂</div>
              <div>Henüz fotoğraf yüklenmedi.</div>
              <div style={{ fontSize: '12px', marginTop: '8px' }}>Sol taraftaki alana fotoğraf ekleyin.</div>
            </div>
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))',
              gap: '10px',
            }}>
              {images.map(img => (
                <div key={img.filename} style={{
                  position: 'relative',
                  borderRadius: '10px',
                  overflow: 'hidden',
                  border: '1px solid rgba(255,255,255,0.1)',
                  background: 'rgba(0,0,0,0.2)',
                  cursor: 'pointer',
                  transition: 'transform 0.2s',
                }}
                  onMouseEnter={e => (e.currentTarget.style.transform = 'scale(1.03)')}
                  onMouseLeave={e => (e.currentTarget.style.transform = 'scale(1)')}
                >
                  <img
                    src={`${API}/api/training/images/${img.filename}/preview`}
                    alt={img.filename}
                    onClick={() => setSelectedPreview(img.filename)}
                    style={{ width: '100%', height: '90px', objectFit: 'cover', display: 'block' }}
                  />
                  <div style={{ padding: '6px', background: 'rgba(0,0,0,0.6)' }}>
                    <div style={{ color: '#94a3b8', fontSize: '10px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {img.filename.replace('pano_', '').substring(0, 10)}
                    </div>
                    <div style={{ color: '#64748b', fontSize: '10px' }}>{img.size_kb} KB</div>
                  </div>
                  <button
                    onClick={e => { e.stopPropagation(); handleDelete(img.filename); }}
                    style={{
                      position: 'absolute', top: '4px', right: '4px',
                      background: 'rgba(239,68,68,0.85)', border: 'none',
                      borderRadius: '50%', width: '22px', height: '22px',
                      color: 'white', cursor: 'pointer', fontSize: '12px',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}
                  >×</button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Eğitim Logları */}
      {status && status.log_lines.length > 0 && (
        <div style={{
          background: '#0a0e1a', borderRadius: '16px', padding: '20px',
          border: '1px solid rgba(255,255,255,0.08)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h3 style={{ margin: 0, color: '#e2e8f0', fontSize: '15px' }}>📋 Eğitim Logları</h3>
            {status.started_at && (
              <span style={{ color: '#64748b', fontSize: '12px' }}>
                Başlangıç: {formatDate(status.started_at)}
                {status.finished_at && ` | Bitiş: ${formatDate(status.finished_at)}`}
              </span>
            )}
          </div>
          <div
            ref={logRef}
            style={{
              background: '#050810', borderRadius: '10px', padding: '16px',
              fontFamily: 'monospace', fontSize: '12px', lineHeight: '1.7',
              maxHeight: '240px', overflowY: 'auto', color: '#94a3b8',
              border: '1px solid rgba(255,255,255,0.05)',
            }}
          >
            {status.log_lines.map((line, i) => (
              <div key={i} style={{
                color: line.startsWith('✅') ? '#22c55e'
                  : line.startsWith('❌') ? '#ef4444'
                  : line.includes('epoch') || line.includes('Epoch') ? '#60a5fa'
                  : '#94a3b8',
              }}>
                {line}
              </div>
            ))}
          </div>
          {status.state === 'running' && (
            <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#f59e0b', animation: 'pulse 1.5s infinite' }} />
              <span style={{ color: '#f59e0b', fontSize: '12px' }}>Eğitim devam ediyor, sayfa otomatik yenileniyor...</span>
            </div>
          )}
        </div>
      )}

      {/* Lightbox Önizleme */}
      {selectedPreview && (
        <div
          onClick={() => setSelectedPreview(null)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 1000, backdropFilter: 'blur(8px)',
          }}
        >
          <div style={{ position: 'relative', maxWidth: '80vw', maxHeight: '80vh' }}>
            <img
              src={`${API}/api/training/images/${selectedPreview}/preview`}
              alt="preview"
              style={{ maxWidth: '100%', maxHeight: '80vh', borderRadius: '16px', boxShadow: '0 20px 60px rgba(0,0,0,0.8)' }}
            />
            <div style={{ position: 'absolute', bottom: '-36px', left: 0, right: 0, textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>
              {selectedPreview} — Kapatmak için tıklayın
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(1.2); }
        }
      `}</style>
    </div>
  );
}
