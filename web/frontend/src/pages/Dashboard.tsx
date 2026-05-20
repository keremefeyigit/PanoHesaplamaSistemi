import React from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

const Dashboard = () => {
  // Örnek pano verileri
  const stats = [
    { label: 'Toplam Tabela', value: '1,284', color: '#2563eb' },
    { label: 'Bu Ay Ölçülen', value: '156', color: '#22c55e' },
    { label: 'Aktif Kurumlar', value: '12', color: '#f59e0b' },
  ];

  return (
    <div className="dashboard">
      <div className="stats-grid">
        {stats.map((stat, i) => (
          <div key={i} className="card stat-card" style={{borderTop: `4px solid ${stat.color}`}}>
            <span className="stat-label">{stat.label}</span>
            <h2 className="stat-value">{stat.value}</h2>
          </div>
        ))}
      </div>

      <div className="dashboard-main">
        <div className="card map-container-box">
          <h3>Pano Dağılım Haritası</h3>
          <div style={{ height: '400px', width: '100%', marginTop: '1rem', borderRadius: '0.5rem', overflow: 'hidden' }}>
            <MapContainer center={[39.9334, 32.8597]} zoom={13} style={{ height: '100%', width: '100%' }}>
              <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              />
              <Marker position={[39.9334, 32.8597]}>
                <Popup>Örnek Pano Konumu</Popup>
              </Marker>
            </MapContainer>
          </div>
        </div>

        <div className="card recent-detections">
          <h3>Son Tespitler</h3>
          <ul className="detection-list">
            <li className="detection-item">
              <div>
                <strong>Billboard - Kızılay</strong>
                <p>12.05.2026 14:20</p>
              </div>
              <span className="area-tag">10.5 m²</span>
            </li>
            <li className="detection-item">
              <div>
                <strong>Raket - Bahçelievler</strong>
                <p>12.05.2026 13:45</p>
              </div>
              <span className="area-tag">2.1 m²</span>
            </li>
          </ul>
        </div>
      </div>

      <style>{`
        .stats-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 1.5rem;
          margin-bottom: 2rem;
        }
        .stat-card {
          text-align: center;
        }
        .stat-label {
          color: var(--text-muted);
          font-size: 0.875rem;
        }
        .stat-value {
          font-size: 2rem;
          margin-top: 0.5rem;
        }
        .dashboard-main {
          display: grid;
          grid-template-columns: 1fr;
          gap: 1.5rem;
        }
        @media (min-width: 900px) {
          .dashboard-main {
            grid-template-columns: 2fr 1fr;
          }
        }
        .detection-list {
          list-style: none;
          margin-top: 1rem;
        }
        .detection-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 0.75rem 0;
          border-bottom: 1px solid #f1f5f9;
        }
        .area-tag {
          background: #eff6ff;
          color: #2563eb;
          padding: 0.25rem 0.5rem;
          border-radius: 4px;
          font-weight: bold;
          font-size: 0.875rem;
        }
      `}</style>
    </div>
  );
};

export default Dashboard;
