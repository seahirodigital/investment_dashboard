import React, { useState, useEffect, useMemo } from 'react';
// ★修正: 絶対パスに変更
import { Icon } from '/investment_dashboard/js/components/Icons.js';


// 以下、ProfitManagerの全コード（変更なし）
const CATEGORY_STYLES = {
    stocks: { bg: 'bg-[#F3E5F5]', text: 'text-[#7E57C2]', label: '現物' },
    margin: { bg: 'bg-[#E8EAF6]', text: 'text-[#5C6BC0]', label: '信用' },
    foreign: { bg: 'bg-[#EDE7F6]', text: 'text-[#673AB7]', label: '海外' },
    cfd: { bg: 'bg-[#FCE4EC]', text: 'text-[#D81B60]', label: 'CFD' },
    event: { bg: 'bg-white', text: 'text-[#7C4DFF]', label: 'Event' }
};

const ProfitManager = () => {
    const [currentDate, setCurrentDate] = useState(new Date());
    const [historyData, setHistoryData] = useState({});
    const [selectedDate, setSelectedDate] = useState(null);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editData, setEditData] = useState({ event: '', stocks: 0, margin: 0, foreign: 0, cfd: 0, note: '' });
    const [modalTab, setModalTab] = useState('edit'); 
    
    const formatMoney = (val) => val ? val.toLocaleString() : '0';
    const getMonthKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    const getDateKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    
    useEffect(() => {
        const saved = localStorage.getItem('history_data');
        if (saved) { try { setHistoryData(JSON.parse(saved)); } catch (e) { console.error(e); } }
    }, []);

    const saveToStorage = (newData) => {
        setHistoryData(newData);
        localStorage.setItem('history_data', JSON.stringify(newData));
    };

    const stats = useMemo(() => {
        let lifetime = 0, prevYear = 0, monthTotal = 0;
        const currentMonthKey = getMonthKey(currentDate);
        const prevYearKey = (currentDate.getFullYear() - 1).toString();
        Object.entries(historyData).forEach(([key, val]) => {
            if (key.match(/^\d{4}-\d{2}-\d{2}$/)) {
                const dayTotal = (val.stocks || 0) + (val.margin || 0) + (val.foreign || 0) + (val.cfd || 0);
                lifetime += dayTotal;
                if (key.startsWith(currentMonthKey)) monthTotal += dayTotal;
                if (key.startsWith(prevYearKey)) prevYear += dayTotal;
            } else if (key === prevYearKey && val.total) prevYear += val.total;
            else if (val.total) lifetime += val.total;
        });
        return { lifetime, prevYear, monthTotal };
    }, [historyData, currentDate]);

    const calendarWeeks = useMemo(() => {
        const year = currentDate.getFullYear(), month = currentDate.getMonth();
        const firstDay = new Date(year, month, 1), lastDay = new Date(year, month + 1, 0);
        const weeks = []; let currentWeek = [];
        for (let i = 0; i < firstDay.getDay(); i++) currentWeek.push(null);
        for (let d = 1; d <= lastDay.getDate(); d++) {
            const date = new Date(year, month, d);
            currentWeek.push(date);
            if (date.getDay() === 6) { weeks.push(currentWeek); currentWeek = []; }
        }
        if (currentWeek.length > 0) { while (currentWeek.length < 7) currentWeek.push(null); weeks.push(currentWeek); }
        return weeks;
    }, [currentDate]);

    const openModal = (date) => {
        if (!date) return;
        const key = getDateKey(date);
        const data = historyData[key] || { event: '', stocks: 0, margin: 0, foreign: 0, cfd: 0, note: '' };
        if (!data.note) data.note = `# ${key.replace(/-/g, '/')}`;
        setSelectedDate(date);
        setEditData({ ...data });
        setModalTab('edit');
        setIsModalOpen(true);
    };

    const handleSave = () => {
        if (!selectedDate) return;
        const key = getDateKey(selectedDate);
        const newData = { ...historyData, [key]: editData };
        saveToStorage(newData);
        setIsModalOpen(false);
    };

    const handleDeleteEvent = (e, date) => {
        e.stopPropagation();
        if (!window.confirm("イベントを削除しますか？")) return;
        const key = getDateKey(date);
        if (historyData[key]) {
            const newData = { ...historyData, [key]: { ...historyData[key], event: '' } };
            saveToStorage(newData);
        }
    };

    const handleExportMD = () => {
        const year = currentDate.getFullYear(), month = currentDate.getMonth() + 1;
        let md = `# 投資日記レポート：${year}年${month}月度\n（月間の総合計収支：${stats.monthTotal > 0 ? '+' : ''}${stats.monthTotal.toLocaleString()}円）\n\n`;
        const sortedKeys = Object.keys(historyData).filter(k => k.startsWith(getMonthKey(currentDate))).sort();
        sortedKeys.forEach(key => {
            const d = historyData[key];
            const total = (d.stocks||0) + (d.margin||0) + (d.foreign||0) + (d.cfd||0);
            if (total === 0 && !d.note && !d.event) return;
            md += `## ${key} ${d.event ? `(${d.event})` : ''}\n### 収支データ\n- 現物: ${d.stocks||0} / 信用: ${d.margin||0} / 海外: ${d.foreign||0} / CFD: ${d.cfd||0}\n### 振り返り\n${d.note || '（記載なし）'}\n\n`;
        });
        const blob = new Blob([md], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = `investment_diary_${year}_${month}.md`; a.click();
    };

    const handleExportCSV = () => {
        const year = currentDate.getFullYear(), month = currentDate.getMonth() + 1;
        const sortedKeys = Object.keys(historyData).filter(k => k.startsWith(getMonthKey(currentDate))).sort();
        let csv = '\uFEFFDate,Event,Stocks,Margin,Foreign,CFD,Total,Note\n';
        sortedKeys.forEach(key => {
            const d = historyData[key];
            const total = (d.stocks||0) + (d.margin||0) + (d.foreign||0) + (d.cfd||0);
            csv += `${key},${d.event ? `"${d.event.replace(/"/g, '""')}"` : ""},${d.stocks||0},${d.margin||0},${d.foreign||0},${d.cfd||0},${total},${d.note ? `"${d.note.replace(/"/g, '""')}"` : ""}\n`;
        });
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = `investment_data_${year}_${month}.csv`; a.click();
    };

    const DayCell = ({ date }) => {
        if (!date) return <div className="cal-cell bg-slate-50"></div>;
        const key = getDateKey(date);
        const data = historyData[key];
        const hasNote = data && data.note && data.note.trim().length > 0;
        const hasEvent = data && data.event && data.event.trim().length > 0;
        const isToday = getDateKey(new Date()) === key;
        const StatCard = ({ type, val }) => (
            <div className={`flex justify-between items-center px-1.5 py-0.5 rounded text-[10px] font-medium mb-0.5 ${CATEGORY_STYLES[type].bg} ${CATEGORY_STYLES[type].text}`}>
                <span>{CATEGORY_STYLES[type].label.charAt(0)}</span><span className={val < 0 ? 'text-[#FF4081]' : ''}>{formatMoney(val)}</span>
            </div>
        );
        return (
            <div onClick={() => openModal(date)} className={`cal-cell cursor-pointer hover:bg-[#F3E5F5] transition-colors border-r border-b border-slate-100 ${isToday ? 'bg-[#F3E5F5]/30 ring-2 ring-inset ring-[#7C4DFF]/20' : ''}`}>
                <div className="flex justify-between items-start mb-1">
                    <span className={`text-xs font-bold ${isToday ? 'bg-[#7C4DFF] text-white px-1.5 py-0.5 rounded-full' : 'text-slate-500'}`}>{date.getDate()}</span>
                    {hasNote && <Icon name="FileText" size={12} className="text-[#64748B]" />}
                </div>
                <div className="flex flex-col gap-0.5">
                    {hasEvent ? (
                        <div className="group relative flex justify-between items-center px-1.5 py-1 rounded text-[10px] font-bold mb-1 bg-white border-l-4 border-[#7C4DFF] shadow-sm text-[#7C4DFF]">
                            <span className="truncate">{data.event}</span>
                            <div className="absolute right-1 top-1/2 -translate-y-1/2 hidden group-hover:flex gap-1 bg-white pl-1">
                                <button onClick={(e) => { e.stopPropagation(); openModal(date); }} className="hover:text-[#7C4DFF]"><Icon name="Pencil" size={10} /></button>
                                <button onClick={(e) => handleDeleteEvent(e, date)} className="hover:text-[#FF4081]"><Icon name="X" size={10} /></button>
                            </div>
                        </div>
                    ) : ( <div className="h-[22px] mb-1"></div> )}
                    {data ? ( <><StatCard type="stocks" val={data.stocks||0} /><StatCard type="margin" val={data.margin||0} /><StatCard type="foreign" val={data.foreign||0} /><StatCard type="cfd" val={data.cfd||0} /></> ) : ( <><div className="h-[18px]"></div><div className="h-[18px]"></div><div className="h-[18px]"></div><div className="h-[18px]"></div></> )}
                </div>
            </div>
        );
    };

    return (
        <div className="space-y-6 mb-12">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 animate-fade-in-up">
                <div className="lifetime-bg rounded-xl p-6 text-white shadow-lg relative overflow-hidden group">
                    <div className="relative z-10"><p className="text-white/80 text-sm font-medium mb-1">生涯収益 (Lifetime Profit)</p><h3 className="text-3xl font-bold tracking-tight">¥ {stats.lifetime.toLocaleString()}</h3><p className="text-xs text-white/60 mt-2">全期間累計</p></div>
                    <div className="absolute right-0 bottom-0 opacity-10 transform translate-x-4 translate-y-4 group-hover:scale-110 transition-transform"><Icon name="LineChart" size={100} /></div>
                </div>
                <div className="bg-white rounded-xl p-6 border border-slate-200 shadow-sm"><p className="text-[#64748B] text-sm font-medium mb-1">前年収支 (2025)</p><h3 className={`text-3xl font-bold ${stats.prevYear >= 0 ? 'text-[#536DFE]' : 'text-[#FF4081]'}`}>{stats.prevYear >= 0 ? '+' : ''}{stats.prevYear.toLocaleString()}</h3><p className="text-xs text-slate-400 mt-2">年間確定損益</p></div>
                <div className="bg-white rounded-xl p-6 border border-slate-200 shadow-sm flex flex-col justify-between"><div><p className="text-[#64748B] text-sm font-medium mb-1">今月収支 ({currentDate.getMonth() + 1}月)</p><h3 className={`text-3xl font-bold ${stats.monthTotal >= 0 ? 'text-[#536DFE]' : 'text-[#FF4081]'}`}>{stats.monthTotal >= 0 ? '+' : ''}{stats.monthTotal.toLocaleString()}</h3></div><p className="text-xs text-slate-400 mt-2">リアルタイム集計</p></div>
            </div>
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden animate-fade-in-up">
                <div className="p-4 border-b border-slate-200 flex justify-between items-center bg-slate-50">
                    <div className="flex items-center gap-4"><h2 className="text-xl font-bold text-[#334155] flex items-center gap-2"><Icon name="Calendar" size={20} />{currentDate.getFullYear()}年 {currentDate.getMonth() + 1}月</h2><div className="flex gap-1"><button onClick={() => setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1))} className="p-1 hover:bg-white hover:shadow rounded text-slate-500"><Icon name="ChevronLeft" size={20} /></button><button onClick={() => setCurrentDate(new Date())} className="px-2 py-1 text-xs font-bold text-slate-600 hover:bg-white hover:shadow rounded">Today</button><button onClick={() => setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1))} className="p-1 hover:bg-white hover:shadow rounded text-slate-500"><Icon name="ChevronRight" size={20} /></button></div></div>
                    <div className="flex gap-2"><button onClick={handleExportMD} className="text-xs flex items-center gap-1 text-slate-600 hover:text-[#7C4DFF] border border-slate-300 rounded px-3 py-1.5 bg-white hover:bg-slate-50 transition-colors shadow-sm font-medium"><Icon name="Download" size={14} /> MD出力</button><button onClick={handleExportCSV} className="text-xs flex items-center gap-1 text-slate-600 hover:text-green-600 border border-slate-300 rounded px-3 py-1.5 bg-white hover:bg-slate-50 transition-colors shadow-sm font-medium"><Icon name="FileCsv" size={14} /> CSV出力</button></div>
                </div>
                <div className="cal-grid">
                    <div className="cal-header">Category</div><div className="cal-header">Mon</div><div className="cal-header">Tue</div><div className="cal-header">Wed</div><div className="cal-header">Thu</div><div className="cal-header">Fri</div><div className="cal-header">週計</div>
                    {calendarWeeks.map((week, wIdx) => {
                        const weekTotal = week.reduce((acc, date) => { if (!date) return acc; const d = historyData[getDateKey(date)]; if (!d) return acc; return { stocks: acc.stocks + (d.stocks||0), margin: acc.margin + (d.margin||0), foreign: acc.foreign + (d.foreign||0), cfd: acc.cfd + (d.cfd||0) }; }, { stocks: 0, margin: 0, foreign: 0, cfd: 0 });
                        const weekSum = weekTotal.stocks + weekTotal.margin + weekTotal.foreign + weekTotal.cfd;
                        return (
                            <React.Fragment key={wIdx}>
                                <div className="cal-label-col border-r border-b border-slate-100"><div className="h-[26px] mb-1"></div>{Object.entries(CATEGORY_STYLES).filter(([k]) => k !== 'event').map(([key, style]) => (<div key={key} className={`text-[10px] font-bold text-center py-0.5 rounded ${style.bg} ${style.text}`}>{style.label}</div>))}</div>
                                {week.slice(1, 6).map((date, dIdx) => (<DayCell key={dIdx} date={date} />))}
                                <div className="cal-total-col border-b border-slate-100 bg-slate-50"><div className="flex flex-col gap-0.5 w-full text-xs"><div className="h-[26px] mb-1"></div><div className={`text-right ${weekTotal.stocks < 0 ? 'text-[#FF4081]' : weekTotal.stocks > 0 ? 'text-[#536DFE]' : 'text-slate-400'}`}>{formatMoney(weekTotal.stocks)}</div><div className={`text-right ${weekTotal.margin < 0 ? 'text-[#FF4081]' : weekTotal.margin > 0 ? 'text-[#536DFE]' : 'text-slate-400'}`}>{formatMoney(weekTotal.margin)}</div><div className={`text-right ${weekTotal.foreign < 0 ? 'text-[#FF4081]' : weekTotal.foreign > 0 ? 'text-[#536DFE]' : 'text-slate-400'}`}>{formatMoney(weekTotal.foreign)}</div><div className={`text-right ${weekTotal.cfd < 0 ? 'text-[#FF4081]' : weekTotal.cfd > 0 ? 'text-[#536DFE]' : 'text-slate-400'}`}>{formatMoney(weekTotal.cfd)}</div><div className={`mt-1 pt-1 border-t border-slate-200 font-bold text-right ${weekSum < 0 ? 'text-[#FF4081]' : 'text-[#334155]'}`}>{formatMoney(weekSum)}</div></div></div>
                            </React.Fragment>
                        );
                    })}
                </div>
            </div>
            {isModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-fade-in-up">
                    <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl h-[80vh] flex flex-col overflow-hidden">
                        <div className="p-4 border-b border-slate-200 flex justify-between items-center bg-slate-50"><h3 className="font-bold text-lg text-[#334155] flex items-center gap-2"><Icon name="FileText" size={20} />{selectedDate.getFullYear()}年{selectedDate.getMonth()+1}月{selectedDate.getDate()}日</h3><button onClick={() => setIsModalOpen(false)} className="text-slate-400 hover:text-slate-600"><Icon name="X" /></button></div>
                        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
                            <div className="w-full md:w-1/3 p-6 border-r border-slate-200 bg-slate-50/50 overflow-y-auto">
                                <div className="mb-6"><label className="block text-xs font-bold text-[#7C4DFF] mb-1 uppercase">Event (Top Layer)</label><input type="text" placeholder="決算, FRB会合, etc." value={editData.event || ''} onChange={(e) => setEditData({...editData, event: e.target.value})} className="w-full border border-purple-200 rounded p-2 text-sm focus:ring-2 focus:ring-[#7C4DFF] outline-none" /></div>
                                <h4 className="text-sm font-bold text-[#64748B] uppercase mb-4">収支入力 (円)</h4>
                                <div className="space-y-4">
                                    {[ { k: 'stocks', l: '現物収支' }, { k: 'margin', l: '信用収支' }, { k: 'foreign', l: '海外株収支' }, { k: 'cfd', l: 'CFD/先物' } ].map(f => (<div key={f.k}><label className="block text-xs font-bold text-slate-500 mb-1">{f.l}</label><input type="number" value={editData[f.k] || ''} onChange={(e) => setEditData({...editData, [f.k]: parseInt(e.target.value) || 0})} className="w-full border border-slate-300 rounded p-2 font-mono text-right focus:ring-2 focus:ring-[#7C4DFF] outline-none" /></div>))}
                                    <div className="pt-4 border-t border-slate-200 mt-4"><div className="flex justify-between items-center"><span className="font-bold text-slate-700">合計</span><span className={`text-xl font-bold font-mono ${(editData.stocks+editData.margin+editData.foreign+editData.cfd) >= 0 ? 'text-[#536DFE]' : 'text-[#FF4081]'}`}>{formatMoney(editData.stocks + editData.margin + editData.foreign + editData.cfd)}</span></div></div>
                                </div>
                            </div>
                            <div className="flex-1 flex flex-col h-full bg-white">
                                <div className="flex border-b border-slate-200 shrink-0"><button onClick={() => setModalTab('edit')} className={`px-6 py-3 text-sm font-bold ${modalTab === 'edit' ? 'text-[#7C4DFF] border-b-2 border-[#7C4DFF]' : 'text-slate-500 hover:bg-slate-50'}`}>編集 (Markdown)</button><button onClick={() => setModalTab('preview')} className={`px-6 py-3 text-sm font-bold ${modalTab === 'preview' ? 'text-[#7C4DFF] border-b-2 border-[#7C4DFF]' : 'text-slate-500 hover:bg-slate-50'}`}>プレビュー</button></div>
                                <div className="flex-1 overflow-hidden relative">{modalTab === 'edit' ? ( <textarea className="w-full h-full p-4 resize-none outline-none font-mono text-sm leading-relaxed" value={editData.note} onChange={(e) => setEditData({...editData, note: e.target.value})} /> ) : ( <div className="w-full h-full p-4 overflow-y-auto markdown-preview" dangerouslySetInnerHTML={{ __html: window.marked ? window.marked.parse(editData.note || '') : editData.note }} /> )}</div>
                            </div>
                        </div>
                        <div className="p-4 border-t border-slate-200 bg-slate-50 flex justify-end gap-3 shrink-0"><button onClick={() => setIsModalOpen(false)} className="px-4 py-2 text-slate-600 hover:bg-slate-200 rounded-lg text-sm font-bold transition-colors">キャンセル</button><button onClick={handleSave} className="px-6 py-2 bg-[#7C4DFF] text-white hover:bg-[#651FFF] rounded-lg text-sm font-bold flex items-center gap-2 transition-colors"><Icon name="Check" size={16} /> 保存</button></div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default ProfitManager;
