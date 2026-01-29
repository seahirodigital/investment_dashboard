import React, { useState } from 'react';
import ReactDOM from 'react-dom/client';

// ★修正: 絶対パスに変更
import { Icon } from '/investment_dashboard/js/components/Icons.js';
import ProfitManager from '/investment_dashboard/js/components/ProfitManager.js';
import ForeignInvestors from '/investment_dashboard/js/components/ForeignInvestors.js';
import ParticipantVolume from '/investment_dashboard/js/components/ParticipantVolume.js';
import OptionOI from '/investment_dashboard/js/components/OptionOI.js';

const App = () => {
    const [view, setView] = useState('calendar');
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [optionCharts, setOptionCharts] = useState([]);
    
    // Custom Links State
    const [customLinks, setCustomLinks] = useState(() => {
        const saved = localStorage.getItem('market-dash-links');
        return saved ? JSON.parse(saved) : [];
    });
    const [isAddingLink, setIsAddingLink] = useState(false);
    const [newLinkLabel, setNewLinkLabel] = useState('');
    const [newLinkUrl, setNewLinkUrl] = useState('');
    const [linkType, setLinkType] = useState('link');
    const [draggedIndex, setDraggedIndex] = useState(null);

    const addCustomLink = () => {
        if (linkType === 'link' && newLinkLabel && newLinkUrl) {
            let url = newLinkUrl;
            if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
            const updated = [...customLinks, { label: newLinkLabel, url, type: 'link' }];
            setCustomLinks(updated);
            localStorage.setItem('market-dash-links', JSON.stringify(updated));
            setNewLinkLabel(''); setNewLinkUrl(''); setIsAddingLink(false);
        } else if (linkType === 'divider' && newLinkLabel) {
            const updated = [...customLinks, { label: newLinkLabel, url: '', type: 'divider' }];
            setCustomLinks(updated);
            localStorage.setItem('market-dash-links', JSON.stringify(updated));
            setNewLinkLabel(''); setNewLinkUrl(''); setIsAddingLink(false);
        }
    };

    const removeCustomLink = (index) => {
        const updated = customLinks.filter((_, i) => i !== index);
        setCustomLinks(updated);
        localStorage.setItem('market-dash-links', JSON.stringify(updated));
    };

    const handleDragStart = (e, index) => { setDraggedIndex(index); e.dataTransfer.effectAllowed = 'move'; };
    const handleDragOver = (e, index) => {
        e.preventDefault();
        if (draggedIndex === null || draggedIndex === index) return;
        const newLinks = [...customLinks];
        const [removed] = newLinks.splice(draggedIndex, 1);
        newLinks.splice(index, 0, removed);
        setCustomLinks(newLinks);
        setDraggedIndex(index);
    };
    const handleDragEnd = () => {
        setDraggedIndex(null);
        localStorage.setItem('market-dash-links', JSON.stringify(customLinks));
    };

    const NavItem = ({ id, label, icon }) => (
        <button onClick={() => { setView(id); setSidebarOpen(false); }} className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${view === id ? 'bg-[#7C4DFF] text-white shadow' : 'text-[#64748B] hover:bg-slate-100'}`}>
            <Icon name={icon} /><span className="font-medium">{label}</span>
        </button>
    );

    return (
        <div className="flex h-screen overflow-hidden">
            <aside className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-white border-r border-slate-200 transform transition-transform ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'} shadow-xl lg:shadow-none flex flex-col`}>
                <div className="h-6"></div>
                <div className="flex-1 overflow-y-auto p-4 space-y-2 flex flex-col relative">
                    <div className="text-xs font-bold text-slate-400 px-2 mb-2">MENU</div>
                    <NavItem id="calendar" label="投資カレンダー" icon="Calendar" />
                    <NavItem id="option" label="Option 分析" icon="BarChart3" />
                    <NavItem id="jpx" label="JPX 海外投資家動向" icon="LineChart" />
                    <NavItem id="participant" label="取引参加者別取引高" icon="Briefcase" />
                    
                    <div className="flex-1 min-h-[20px]"></div>
                    {customLinks.length > 0 && (
                        <div className="space-y-1 mb-4 pb-12">
                            <div className="text-xs font-bold text-slate-400 px-2 mb-2">QUICK LINKS</div>
                            <div className="flex flex-col gap-1">
                                {customLinks.map((link, i) => (
                                    <div key={i} draggable onDragStart={(e) => handleDragStart(e, i)} onDragOver={(e) => handleDragOver(e, i)} onDragEnd={handleDragEnd} className={`group flex items-center gap-2 px-3 py-1 rounded-lg transition-colors cursor-move ${draggedIndex === i ? 'dragging' : ''} ${link.type === 'divider' ? 'mt-2 mb-1' : 'hover:bg-slate-100'}`}>
                                        <div className="text-slate-300 group-hover:text-slate-400 cursor-grab active:cursor-grabbing"><Icon name="GripVertical" size={14} /></div>
                                        {link.type === 'divider' ? (
                                            <div className="flex-1 flex items-center gap-2 text-slate-400 text-xs font-bold uppercase tracking-wider overflow-hidden"><Icon name="FolderOpen" size={12} /><span className="truncate">{link.label}</span><div className="flex-1 h-px bg-slate-200 ml-2"></div></div>
                                        ) : (
                                            <a href={link.url} target="_blank" rel="noopener noreferrer" className="flex-1 flex items-center gap-2 text-slate-600 text-sm font-medium overflow-hidden pointer-events-none group-hover:pointer-events-auto"><Icon name="ExternalLink" size={14} className="shrink-0" /><span className="truncate">{link.label}</span></a>
                                        )}
                                        <button onClick={() => removeCustomLink(i)} className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-500 transition-opacity"><Icon name="Trash2" size={12} /></button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                    <div className="absolute bottom-4 left-0 right-0 px-4 flex justify-center">
                        {!isAddingLink ? (
                            <button onClick={() => setIsAddingLink(true)} className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-50 border border-slate-200 text-slate-400 hover:text-[#7C4DFF] hover:bg-white hover:shadow-md transition-all duration-200" title="リンクを追加"><Icon name="Plus" size={20} /></button>
                        ) : (
                            <div className="w-full bg-white rounded-xl shadow-xl border border-slate-200 p-4 animate-fade-in-up">
                                <div className="flex justify-between items-center mb-3"><p className="text-xs font-bold text-slate-500 uppercase">Add Item</p><button onClick={() => setIsAddingLink(false)} className="text-slate-400 hover:text-slate-600"><Icon name="X" size={14}/></button></div>
                                <div className="flex bg-slate-100 p-1 rounded-lg mb-3">
                                    <button onClick={() => setLinkType('link')} className={`flex-1 text-xs py-1.5 rounded-md font-bold transition-all ${linkType === 'link' ? 'bg-white text-[#7C4DFF] shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>LINK</button>
                                    <button onClick={() => setLinkType('divider')} className={`flex-1 text-xs py-1.5 rounded-md font-bold transition-all ${linkType === 'divider' ? 'bg-white text-[#7C4DFF] shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>CATEGORY</button>
                                </div>
                                <div className="space-y-3">
                                    <input type="text" placeholder="Name" autoFocus className="w-full text-xs p-2 border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-[#7C4DFF] focus:border-[#7C4DFF] transition-all" value={newLinkLabel} onChange={(e) => setNewLinkLabel(e.target.value)} />
                                    {linkType === 'link' && (<input type="text" placeholder="URL" className="w-full text-xs p-2 border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-[#7C4DFF] focus:border-[#7C4DFF] transition-all" value={newLinkUrl} onChange={(e) => setNewLinkUrl(e.target.value)} />)}
                                    <button onClick={addCustomLink} disabled={!newLinkLabel || (linkType === 'link' && !newLinkUrl)} className="w-full bg-[#7C4DFF] text-white text-xs py-2 rounded-lg hover:bg-[#651FFF] disabled:opacity-50 font-bold transition-colors">追加</button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </aside>
            {sidebarOpen && <div className="fixed inset-0 bg-black/50 z-40 lg:hidden" onClick={() => setSidebarOpen(false)}></div>}
            <div className="flex-1 flex flex-col min-w-0">
                <header className="h-16 bg-white border-b border-slate-200 flex items-center px-4 lg:hidden shrink-0">
                    <button onClick={() => setSidebarOpen(true)} className="p-2 text-slate-600"><Icon name="Menu" /></button>
                    <span className="ml-4 font-bold text-[#334155]">{view === 'calendar' ? '投資カレンダー' : view === 'option' ? 'Option 分析' : view === 'jpx' ? 'JPX 海外投資家動向' : '取引参加者別取引高'}</span>
                </header>
                <main className="flex-1 overflow-auto p-4 md:p-6 bg-slate-50">
                    <div className="max-w-7xl mx-auto h-full">
                        {view === 'calendar' ? <ProfitManager /> : view === 'jpx' ? <ForeignInvestors /> : view === 'participant' ? <ParticipantVolume /> : <OptionOI charts={optionCharts} setCharts={setOptionCharts} />}
                    </div>
                </main>
            </div>
        </div>
    );
};

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
