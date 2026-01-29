import React, { useState, useEffect, useRef } from 'react';
import Papa from 'papaparse';
import { Chart } from 'recharts';
// ★修正: 同じcomponentsフォルダ内なので ./Icons.js に変更
import { Icon } from './Icons.js';

// --- Logic Helpers ---
const processOptionData = (rawRows, step = 50) => {
    if (!rawRows || rawRows.length < 2) return { data: [], error: 'データが不足しています。' };
    const strikeRegex = /(strike|行使価格|koushi)/i;
    const oiRegex = /(open\s*int|oi|建玉|tategyoku)/i;
    const parseNum = (val) => {
        if (typeof val === 'number') return val;
        if (!val) return 0;
        let str = String(val).toUpperCase();
        let multiplier = 1;
        if (str.endsWith('K')) multiplier = 1000;
        else if (str.endsWith('M')) multiplier = 1000000;
        str = str.replace(/[^0-9.-]/g, '').trim(); 
        const num = parseFloat(str);
        return isNaN(num) ? 0 : num * multiplier;
    };

    let reshapeHeaderIndex = -1;
    let reshapeWidth = 0;
    const getHeaderInfo = (row) => {
        const sRow = row.map(c => String(c).trim());
        let sCol = -1, oiCols = [];
        sRow.forEach((cell, i) => { if (strikeRegex.test(cell)) sCol = i; else if (oiRegex.test(cell)) oiCols.push(i); });
        return { sCol, oiCols, colCount: row.length };
    };

    for (let r = 0; r < Math.min(rawRows.length, 50); r++) {
        const info = getHeaderInfo(rawRows[r]);
        if (info.sCol !== -1 && info.oiCols.length >= 2 && info.colCount > 1) {
            let singleColCount = 0;
            for(let k=1; k<=10 && (r+k)<rawRows.length; k++) { if (rawRows[r+k].length === 1 || rawRows[r+k].length < info.colCount / 2) singleColCount++; }
            if (singleColCount >= 5) { reshapeHeaderIndex = r; reshapeWidth = info.colCount; break; }
        }
    }

    if (reshapeWidth > 0 && reshapeHeaderIndex !== -1) {
        const headerRow = rawRows[reshapeHeaderIndex];
        const flatData = [];
        for (let i = reshapeHeaderIndex + 1; i < rawRows.length; i++) {
            const row = rawRows[i];
            for (const cell of row) { if (cell !== null && cell !== undefined && String(cell).trim() !== '') flatData.push(cell); }
        }
        const newRows = [headerRow];
        let currentChunk = [];
        for (const cell of flatData) {
            currentChunk.push(cell);
            if (currentChunk.length === reshapeWidth) { newRows.push(currentChunk); currentChunk = []; }
        }
        rawRows = newRows;
    }

    let bestCandidate = { headerIndex: -1, strikeCol: -1, callCol: -1, putCol: -1, score: 0 };
    for (let r = 0; r < Math.min(rawRows.length, 50); r++) {
        const row = rawRows[r].map(c => String(c).trim());
        let sCol = -1, oiCols = [];
        row.forEach((cell, i) => { if (strikeRegex.test(cell)) sCol = i; else if (oiRegex.test(cell)) oiCols.push(i); });
        if (sCol !== -1 && oiCols.length >= 2) {
            let cCol = -1, pCol = -1;
            const oi1 = row[oiCols[0]].toLowerCase();
            const oi2 = row[oiCols[1]].toLowerCase();
            if (oi1.includes('call') || oi1.includes('コール')) { cCol = oiCols[0]; }
            if (oi1.includes('put') || oi1.includes('プット')) { pCol = oiCols[0]; }
            if (oi2.includes('call') || oi2.includes('コール')) { cCol = oiCols[1]; }
            if (oi2.includes('put') || oi2.includes('プット')) { pCol = oiCols[1]; }
            if (cCol === -1 || pCol === -1) { cCol = oiCols[0]; pCol = oiCols[1]; }
            bestCandidate = { headerIndex: r, strikeCol: sCol, callCol: cCol, putCol: pCol, score: 10 };
            break;
        }
    }

    if (bestCandidate.headerIndex === -1) return { data: [], error: 'ヘッダーが見つかりませんでした。' };

    const { headerIndex, strikeCol, callCol, putCol } = bestCandidate;
    const dataMap = new Map();
    const safeStep = step > 0 ? step : 1;

    for (let i = headerIndex + 1; i < rawRows.length; i++) {
        const row = rawRows[i];
        if (!row || row.length <= Math.max(strikeCol, callCol, putCol)) continue;
        const strike = parseNum(row[strikeCol]);
        const oi1 = parseNum(row[callCol]);
        const oi2 = parseNum(row[putCol]);
        if (strike > 0) {
            const roundedStrike = Math.round(strike / safeStep) * safeStep;
            if (!dataMap.has(roundedStrike)) dataMap.set(roundedStrike, { call: 0, put: 0 });
            const d = dataMap.get(roundedStrike);
            d.call += oi1;
            d.put += oi2;
        }
    }

    const sortedData = Array.from(dataMap.entries())
        .sort((a, b) => b[0] - a[0])
        .map(([strike, val]) => ({ strike, diff: val.call - val.put, call: val.call, put: val.put }));

    return { data: sortedData, error: sortedData.length === 0 ? "有効なデータが見つかりませんでした" : null };
};

// --- Sub Components ---
const DataInput = ({ onDataParsed }) => {
    const [text, setText] = useState('');
    const [dragActive, setDragActive] = useState(false);
    const handleParse = (input) => {
        Papa.parse(input, {
            complete: (results) => onDataParsed(results.data),
            skipEmptyLines: true,
            header: false 
        });
    };
    const handleDrop = (e) => {
        e.preventDefault();
        setDragActive(false);
        if (e.dataTransfer.files?.[0]) handleParse(e.dataTransfer.files[0]);
    };
    return (
        <div className="max-w-3xl mx-auto bg-white rounded-xl shadow border border-slate-200 p-6 space-y-6">
            <div 
                className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${dragActive ? 'border-[#7C4DFF] bg-purple-50' : 'border-slate-300 hover:bg-slate-50'}`}
                onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                onDragLeave={() => setDragActive(false)}
                onDrop={handleDrop}
            >
                <Icon name="Upload" className="mx-auto text-slate-400 mb-2" size={32} />
                <p className="text-slate-600 font-medium">CSVファイルをドラッグ＆ドロップ</p>
                <p className="text-slate-400 text-sm">または</p>
                <input type="file" className="mt-2 text-sm text-slate-500" onChange={(e) => e.target.files?.[0] && handleParse(e.target.files[0])} />
            </div>
            <div className="flex gap-2">
                <textarea 
                    className="flex-1 border border-slate-300 rounded-lg p-3 text-sm font-mono focus:ring-2 focus:ring-[#7C4DFF] outline-none"
                    rows={4}
                    placeholder="ここにデータを貼り付け..."
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                />
                <button onClick={() => handleParse(text)} disabled={!text} className="bg-[#7C4DFF] text-white px-4 rounded-lg hover:bg-[#651FFF] disabled:opacity-50 font-medium">解析</button>
            </div>
        </div>
    );
};

const OIChart = ({ id, initialData, initialStep, rawRows, onStepChange }) => {
    const [data, setData] = useState(initialData);
    const [step, setStep] = useState(initialStep);
    
    // Recharts Controls
    const [zoomY, setZoomY] = useState(1);
    const [zoomX, setZoomX] = useState(1);
    const mainRef = useRef(null);
    const leftRef = useRef(null);
    const bottomRef = useRef(null);

    // Step変更時に再計算
    useEffect(() => {
        if(rawRows && step !== initialStep) {
            const res = processOptionData(rawRows, step);
            if(!res.error) {
                setData(res.data);
                onStepChange(id, step, res.data);
            }
        }
    }, [step]);

    const handleScroll = () => {
        if (mainRef.current && leftRef.current && bottomRef.current) {
            leftRef.current.scrollTop = mainRef.current.scrollTop;
            bottomRef.current.scrollLeft = mainRef.current.scrollLeft;
        }
    };
    const barHeight = 30;
    const totalHeight = Math.max(450, data.length * barHeight * zoomY);
    const chartWidth = `${zoomX * 100}%`;
    const maxVal = Math.max(...data.map(d => Math.abs(d.diff)), 100);
    
    const handleWheel = (e, axis) => {
        if (e.ctrlKey || axis === 'main') return; 
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.1 : 0.1;
        if (axis === 'y') setZoomY(z => Math.max(0.1, Math.min(5, z + delta)));
        if (axis === 'x') setZoomX(z => Math.max(0.5, Math.min(3, z + delta)));
    };

    const CustomTooltip = ({ active, payload, label }) => {
        if (!active || !payload?.length) return null;
        const d = payload[0].payload;
        return (
            <div className="bg-white p-3 border border-slate-200 shadow-lg rounded text-sm z-50">
                <p className="font-bold">Strike: {label}</p>
                <p className={d.diff >= 0 ? 'text-[#536DFE]' : 'text-[#FF4081]'}>Diff: {d.diff.toLocaleString()}</p>
                <div className="text-xs text-slate-500 mt-1 pt-1 border-t">C: {d.call.toLocaleString()} / P: {d.put.toLocaleString()}</div>
            </div>
        );
    };

    return (
        <div className="bg-white rounded-xl shadow border border-slate-200 h-[80vh] flex flex-col overflow-hidden mb-6 animate-fade-in-up">
            <div className="p-2 border-b border-slate-100 flex items-center gap-4 bg-slate-50 shrink-0 flex-wrap">
                <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-500">HEIGHT</span>
                    <button onClick={()=>setZoomY(z=>Math.max(0.1, z-0.2))} className="p-1 hover:bg-slate-200 rounded"><Icon name="ZoomOut" size={16}/></button>
                    <input type="range" min="0.1" max="5" step="0.1" value={zoomY} onChange={(e)=>setZoomY(parseFloat(e.target.value))} className="w-20" />
                    <button onClick={()=>setZoomY(z=>Math.min(5, z+0.2))} className="p-1 hover:bg-slate-200 rounded"><Icon name="ZoomIn" size={16}/></button>
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-500">WIDTH</span>
                    <button onClick={()=>setZoomX(z=>Math.max(0.5, z-0.2))} className="p-1 hover:bg-slate-200 rounded"><Icon name="ZoomOut" size={16}/></button>
                    <button onClick={()=>setZoomX(z=>Math.min(3, z+0.2))} className="p-1 hover:bg-slate-200 rounded"><Icon name="ZoomIn" size={16}/></button>
                </div>
                <div className="flex items-center gap-2 border-l pl-4 border-slate-200">
                    <span className="text-xs font-bold text-slate-500">STEP</span>
                    <input 
                        type="number" 
                        className="border border-slate-300 rounded px-1 py-0.5 text-xs w-16 text-center focus:outline-none focus:border-[#7C4DFF]"
                        value={step}
                        onChange={(e) => setStep(parseFloat(e.target.value) || 0)}
                        min="0.1"
                    />
                </div>
                <button onClick={()=>{setZoomY(1);setZoomX(1);}} className="ml-auto text-xs flex items-center gap-1 hover:text-[#7C4DFF] border px-2 py-1 rounded bg-white"><Icon name="RotateCcw" size={14}/> Reset</button>
            </div>
            <div className="flex-1 flex overflow-hidden relative">
                <div className="w-24 border-r border-slate-200 bg-slate-50 shrink-0 overflow-hidden" ref={leftRef} onWheel={(e)=>handleWheel(e, 'y')}>
                    <div style={{height: totalHeight, width: '100%'}}>
                        <ResponsiveContainer>
                            <BarChart layout="vertical" data={data} margin={{top:10, bottom:0}}>
                                <YAxis type="category" dataKey="strike" width={90} tick={{fontSize:12, fontWeight:600}} interval={0} />
                                <Bar dataKey="diff" fill="transparent" />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
                <div className="flex-1 overflow-auto bg-slate-50/30" ref={mainRef} onScroll={handleScroll}>
                    <div style={{width: chartWidth, height: totalHeight, minWidth: '100%'}}>
                        <ResponsiveContainer>
                            <BarChart layout="vertical" data={data} margin={{top:10, right:30, left:0, bottom:0}}>
                                <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={true} />
                                <XAxis type="number" domain={[-maxVal, maxVal]} hide />
                                <YAxis type="category" width={0} tick={false} />
                                <Tooltip content={<CustomTooltip />} cursor={{fill:'rgba(0,0,0,0.05)'}} />
                                <ReferenceLine x={0} stroke="#334155" />
                                <Bar dataKey="diff" barSize={barHeight * 0.8}>
                                    {data.map((entry, index) => (<Cell key={index} fill={entry.diff >= 0 ? '#536DFE' : '#FF4081'} />))}
                                    <LabelList dataKey="diff" position="insideRight" formatter={(v)=>v.toLocaleString()} style={{fontSize:11, fill:'#64748b'}} />
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
            <div className="h-8 border-t border-slate-200 flex shrink-0">
                <div className="w-24 border-r border-slate-200 bg-slate-100 flex items-center justify-center text-slate-400"><Icon name="MousePointer2" size={14} /></div>
                <div className="flex-1 overflow-hidden bg-slate-50" ref={bottomRef} onWheel={(e)=>handleWheel(e, 'x')}>
                    <div style={{width: chartWidth, minWidth:'100%', height:'100%'}}>
                        <ResponsiveContainer>
                            <BarChart layout="vertical" data={[{}]} margin={{right:30, left:0}}>
                                <XAxis type="number" domain={[-maxVal, maxVal]} tick={{fontSize:10}} />
                                <YAxis type="category" width={0} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default OptionOI;
