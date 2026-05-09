import React, { useState } from 'react';

interface Institution {
  id: number;
  name: string;
  files: number;
  status: string;
}

const Institutions = () => {
  const [institutions, setInstitutions] = useState<Institution[]>([
    { id: 1, name: 'Ankara Büyükşehir Belediyesi', files: 45, status: 'Aktif' },
    { id: 2, name: 'İstanbul Reklam A.Ş.', files: 128, status: 'Aktif' },
    { id: 3, name: 'Kızılay Derneği', files: 12, status: 'Beklemede' },
  ]);

  const [showModal, setShowModal] = useState(false);
  const [newName, setNewName] = useState('');

  const handleAdd = () => {
    if (!newName) return;
    const newInst = {
      id: Date.now(),
      name: newName,
      files: 0,
      status: 'Aktif'
    };
    setInstitutions([...institutions, newInst]);
    setNewName('');
    setShowModal(false);
  };

  const handleDelete = (id: number) => {
    if (window.confirm('Bu kurumu silmek istediğinize emin misiniz?')) {
      setInstitutions(institutions.filter(inst => inst.id !== id));
    }
  };

  const handleView = (name: string) => {
    alert(`${name} kurumuna ait veriler yükleniyor...`);
  };

  const handleShare = (name: string) => {
    alert(`${name} verileri için paylaşım linki oluşturuldu.`);
  };

  return (
    <div className="institutions-page">
      <div className="card">
        <div className="header-actions">
          <h3>Kayıtlı Kurumlar</h3>
          <button className="primary" onClick={() => setShowModal(true)}>+ Yeni Kurum Ekle</button>
        </div>
        
        <table className="inst-table">
          <thead>
            <tr>
              <th>Kurum Adı</th>
              <th>Veri Sayısı (Dosya)</th>
              <th>Durum</th>
              <th>İşlemler</th>
            </tr>
          </thead>
          <tbody>
            {institutions.map(inst => (
              <tr key={inst.id}>
                <td><strong>{inst.name}</strong></td>
                <td>{inst.files} Kayıt</td>
                <td>
                  <span className={`status-pill ${inst.status.toLowerCase()}`}>
                    {inst.status}
                  </span>
                </td>
                <td>
                  <button className="action-btn view" onClick={() => handleView(inst.name)}>Görüntüle</button>
                  <button className="action-btn share" onClick={() => handleShare(inst.name)}>Paylaş</button>
                  <button className="action-btn delete" onClick={() => handleDelete(inst.id)}>Sil</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showModal && (
        <div className="modal-overlay">
          <div className="card modal-content">
            <h4>Yeni Kurum Ekle</h4>
            <input 
              type="text" 
              placeholder="Kurum Adı" 
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="modal-input"
            />
            <div className="modal-actions">
              <button onClick={() => setShowModal(false)}>İptal</button>
              <button className="primary" onClick={handleAdd}>Ekle</button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .header-actions {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1.5rem;
        }
        .inst-table {
          width: 100%;
          border-collapse: collapse;
        }
        .inst-table th {
          text-align: left;
          padding: 1rem;
          background: #f8fafc;
          border-bottom: 2px solid #e2e8f0;
        }
        .inst-table td {
          padding: 1rem;
          border-bottom: 1px solid #e2e8f0;
        }
        .status-pill {
          padding: 0.25rem 0.5rem;
          border-radius: 1rem;
          font-size: 0.75rem;
          font-weight: bold;
        }
        .status-pill.aktif {
          background: #dcfce7;
          color: #166534;
        }
        .status-pill.beklemede {
          background: #fef3c7;
          color: #92400e;
        }
        .action-btn {
          margin-right: 0.5rem;
          font-size: 0.875rem;
          padding: 0.25rem 0.5rem;
          border: 1px solid #e2e8f0;
          border-radius: 4px;
          background: white;
          cursor: pointer;
          transition: all 0.2s;
        }
        .action-btn:hover { background: #f1f5f9; }
        .action-btn.delete { color: #dc2626; border-color: #fecaca; }
        .action-btn.delete:hover { background: #fef2f2; }
        .action-btn.view { color: #2563eb; }
        .action-btn.share { color: #0891b2; }

        .modal-overlay {
          position: fixed;
          inset: 0;
          background: rgba(0,0,0,0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
        }
        .modal-content {
          width: 400px;
        }
        .modal-input {
          width: 100%;
          padding: 0.75rem;
          margin: 1rem 0;
          border: 1px solid #e2e8f0;
          border-radius: 0.375rem;
        }
        .modal-actions {
          display: flex;
          justify-content: flex-end;
          gap: 0.5rem;
        }
      `}</style>
    </div>
  );
};

export default Institutions;
