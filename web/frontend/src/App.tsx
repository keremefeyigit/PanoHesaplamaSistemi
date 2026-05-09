import React, { useState } from 'react';
import Dashboard from './pages/Dashboard';
import LiveView from './pages/LiveView';
import Institutions from './pages/Institutions';
import './App.css';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');

  return (
    <div className="app-layout">
      <nav className="sidebar">
        <div className="logo">PanoHesaplama</div>
        <ul className="nav-links">
          <li className={activeTab === 'dashboard' ? 'active' : ''} onClick={() => setActiveTab('dashboard')}>
            Ana Sayfa
          </li>
          <li className={activeTab === 'live' ? 'active' : ''} onClick={() => setActiveTab('live')}>
            Canlı Takip
          </li>
          <li className={activeTab === 'institutions' ? 'active' : ''} onClick={() => setActiveTab('institutions')}>
            Kurum Yönetimi
          </li>
        </ul>
      </nav>
      
      <main className="content">
        <header className="top-bar">
          <h1>{activeTab === 'dashboard' ? 'Genel Bakış' : activeTab === 'live' ? 'Canlı Ölçüm' : 'Kurumlar'}</h1>
          <div className="user-profile">Admin</div>
        </header>

        <div className="page-container">
          {activeTab === 'dashboard' && <Dashboard />}
          {activeTab === 'live' && <LiveView />}
          {activeTab === 'institutions' && <Institutions />}
        </div>
      </main>
    </div>
  );
}

export default App;
