import React, { useState, useEffect } from 'react';

interface Institution {
  id: number;
  name: string;
  files: number;
  status: string;
  contactInfo?: string;
  renewalDate?: string;
}

const defaultInstitutions: Institution[] = [
  { id: 1, name: 'Ankara Büyükşehir Belediyesi', files: 45, status: 'Aktif', contactInfo: 'info@ankara.bel.tr', renewalDate: '2027-01-01' },
  { id: 2, name: 'İstanbul Reklam A.Ş.', files: 128, status: 'Aktif', contactInfo: 'iletisim@reklam.ist', renewalDate: '2026-12-31' },
  { id: 3, name: 'Kızılay Derneği', files: 12, status: 'Beklemede', contactInfo: 'iletisim@kizilay.org.tr', renewalDate: '2026-08-15' },
];

const Institutions = () => {
  const [institutions, setInstitutions] = useState<Institution[]>(() => {
    const saved = localStorage.getItem('institutionsData');
    if (saved) {
      return JSON.parse(saved);
    }
    return defaultInstitutions;
  });

  useEffect(() => {
    localStorage.setItem('institutionsData', JSON.stringify(institutions));
  }, [institutions]);

  const [showAddModal, setShowAddModal] = useState(false);
  const [showViewModal, setShowViewModal] = useState(false);
  
  // Form States
  const [newName, setNewName] = useState('');
  const [newContactInfo, setNewContactInfo] = useState('');
  const [newRenewalDate, setNewRenewalDate] = useState('');
  
  const [selectedInst, setSelectedInst] = useState<Institution | null>(null);

  const handleAdd = () => {
    if (!newName) return;
    const newInst: Institution = {
      id: Date.now(),
      name: newName,
      files: 0,
      status: 'Aktif',
      contactInfo: newContactInfo,
      renewalDate: newRenewalDate,
    };
    setInstitutions([...institutions, newInst]);
    setNewName('');
    setNewContactInfo('');
    setNewRenewalDate('');
    setShowAddModal(false);
  };

  const handleDelete = (id: number) => {
    if (window.confirm('Bu kurumu silmek istediğinize emin misiniz?')) {
      setInstitutions(institutions.filter(inst => inst.id !== id));
    }
  };

  const handleShare = (name: string) => {
    alert(`${name} verileri için paylaşım linki oluşturuldu.`);
  };

  const openViewModal = (inst: Institution) => {
    setSelectedInst(inst);
    setShowViewModal(true);
  };

  const handleUpdate = () => {
    if (selectedInst) {
      setInstitutions(institutions.map(inst => inst.id === selectedInst.id ? selectedInst : inst));
      setShowViewModal(false);
    }
  };

  return (
    <div className="institutions-page">
      <div className="card">
        <div className="header-actions">
          <h3>Kayıtlı Kurumlar</h3>
          <button className="primary" onClick={() => setShowAddModal(true)}>+ Yeni Kurum Ekle</button>
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
                  <button className="action-btn view" onClick={() => openViewModal(inst)}>Görüntüle</button>
                  <button className="action-btn share" onClick={() => handleShare(inst.name)}>Paylaş</button>
                  <button className="action-btn delete" onClick={() => handleDelete(inst.id)}>Sil</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showAddModal && (
        <div className="modal-overlay">
          <div className="card modal-content">
            <h4>Yeni Kurum Ekle</h4>
            <div className="input-group">
              <label>Kurum Adı</label>
              <input type="text" placeholder="Kurum Adı" value={newName} onChange={(e) => setNewName(e.target.value)} className="modal-input" />
            </div>
            <div className="input-group">
              <label>Kişisel/Kurumsal Bilgiler (E-posta, Tel vs.)</label>
              <input type="text" placeholder="İletişim Bilgileri" value={newContactInfo} onChange={(e) => setNewContactInfo(e.target.value)} className="modal-input" />
            </div>
            <div className="input-group">
              <label>Abonelik Yenileme Tarihi</label>
              <input type="date" value={newRenewalDate} onChange={(e) => setNewRenewalDate(e.target.value)} className="modal-input" />
            </div>
            <div className="modal-actions">
              <button onClick={() => setShowAddModal(false)}>İptal</button>
              <button className="primary" onClick={handleAdd}>Ekle</button>
            </div>
          </div>
        </div>
      )}

      {showViewModal && selectedInst && (
        <div className="modal-overlay">
          <div className="card modal-content">
            <h4>Kurum Detayları</h4>
            <div className="input-group">
              <label>Kurum Adı</label>
              <input type="text" value={selectedInst.name} onChange={(e) => setSelectedInst({...selectedInst, name: e.target.value})} className="modal-input" />
            </div>
            <div className="input-group">
              <label>Kişisel/Kurumsal Bilgiler (E-posta, Tel vs.)</label>
              <input type="text" value={selectedInst.contactInfo || ''} onChange={(e) => setSelectedInst({...selectedInst, contactInfo: e.target.value})} className="modal-input" />
            </div>
            <div className="input-group">
              <label>Abonelik Yenileme Tarihi</label>
              <input type="date" value={selectedInst.renewalDate || ''} onChange={(e) => setSelectedInst({...selectedInst, renewalDate: e.target.value})} className="modal-input" />
            </div>
            <div className="input-group">
              <label>Durum</label>
              <select value={selectedInst.status} onChange={(e) => setSelectedInst({...selectedInst, status: e.target.value})} className="modal-input">
                <option value="Aktif">Aktif</option>
                <option value="Beklemede">Beklemede</option>
                <option value="Pasif">Pasif</option>
              </select>
            </div>
            <div className="modal-actions">
              <button onClick={() => setShowViewModal(false)}>Kapat</button>
              <button className="primary" onClick={handleUpdate}>Kaydet</button>
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
        .status-pill.pasif {
          background: #fee2e2;
          color: #991b1b;
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
          width: 450px;
          max-height: 90vh;
          overflow-y: auto;
        }
        .input-group {
          margin: 1rem 0;
        }
        .input-group label {
          display: block;
          font-size: 0.875rem;
          font-weight: 500;
          color: #475569;
          margin-bottom: 0.5rem;
        }
        .modal-input {
          width: 100%;
          padding: 0.75rem;
          border: 1px solid #cbd5e1;
          border-radius: 0.375rem;
          background: #f8fafc;
        }
        .modal-actions {
          display: flex;
          justify-content: flex-end;
          gap: 0.5rem;
          margin-top: 1.5rem;
        }
      `}</style>
    </div>
  );
};

export default Institutions;
