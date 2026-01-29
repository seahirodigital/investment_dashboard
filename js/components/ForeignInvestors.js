import React, { useState, useEffect, useRef } from 'react';
import Papa from 'papaparse';
import { Chart } from 'recharts'; // Dummy import to keep linter happy if using import map

const ForeignInvestors = () => {
    const chartRef = useRef(null);
    const chartInstance = useRef(null);
    
    const [allData, setAllData] = useState([]);
    const [currentTimeRange, setCurrentTimeRange] = useState('all');
    const [stats, setStats] = useState(null);
    const [dataCount, setDataCount] = useState(0);
    const [lastUpdate, setLastUpdate] = useState('データ取得中...');

    useEffect(() => {
        const canvas = chartRef.current;
        if (!canvas) return;

        const handleWheel = (e) => {
            if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
                e.preventDefault();
            }
        };

        canvas.addEventListener('wheel', handleWheel, { passive: false });
        return () => canvas.removeEventListener('wheel', handleWheel);
    }, [allData]);

    // --- Helper Functions ---
    const formatNumber = (num) => Math.round(num).toLocaleString('ja-JP');
    const formatLargeNumber = (value) => {
        if (typeof value === 'number') {
            const sign = value >= 0 ? '+' : '';
            return sign + formatNumber(value) + '億円';
        }
        return value.toString();
    };

    const calculateWeekLabels = (data) => {
        const weekCounter = {};
        return data.map(row => {
            const date = new Date(row.date);
            const year = date.getFullYear();
            const month = date.getMonth() + 1;
            const yearMonthKey = `${year}-${month}`;
            if (!weekCounter[yearMonthKey]) weekCounter[yearMonthKey] = 1;
            else weekCounter[yearMonthKey]++;
            const weekNum = weekCounter[yearMonthKey];
            return {
                ...row,
                displayDate: `${year}年${month}月${weekNum}週`,
                tooltipDate: `${year}年${month}月第${weekNum}週`
            };
        });
    };

    const calculateStats = (data) => {
        const positiveData = data.filter(item => item.balance > 0).map(item => item.balance);
        const negativeData = data.filter(item => item.balance < 0).map(item => item.balance);
        const calcMedian = (arr) => {
            if (arr.length === 0) return 0;
            const sorted = [...arr].sort((a, b) => a - b);
            const mid = Math.floor(sorted.length / 2);
            return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
        };
        const calcAverage = (arr) => arr.length === 0 ? 0 : arr.reduce((sum, val) => sum + val, 0) / arr.length;
        return {
            positiveAvg: calcAverage(positiveData),
            positiveMedian: calcMedian(positiveData),
            negativeAvg: calcAverage(negativeData),
            negativeMedian: calcMedian(negativeData),
            latest: data[data.length - 1]
        };
    };

    const getFormattedReleaseDate = (lastDateStr) => {
        try {
            const date = new Date(lastDateStr);
            if (isNaN(date.getTime())) return lastDateStr;
            const releaseDate = new Date(date);
            releaseDate.setDate(date.getDate() + 6);
            const y = releaseDate.getFullYear();
            const m = String(releaseDate.getMonth() + 1).padStart(2, '0');
            const d = String(releaseDate.getDate()).padStart(2, '0');
            return `${y}-${m}-${d}-18:00`;
        } catch (e) {
            return lastDateStr;
        }
    };

    // --- Chart Actions ---
    const zoomChart = (direction) => {
        if (!chartInstance.current) return;
        chartInstance.current.zoom(direction === 'in' ? 1.2 : 0.8);
        updateStatsFromChart();
    };
    const panChart = (direction) => {
        if (!chartInstance.current) return;
        const chart = chartInstance.current;
        const range = chart.scales.x.max - chart.scales.x.min;
        chart.pan({ x: direction === 'left' ? range * 0.2 : -range * 0.2 });
        updateStatsFromChart();
    };
    const resetZoom = () => {
        if (!chartInstance.current) return;
        chartInstance.current.resetZoom();
        updateStatsFromChart();
    };

    const updateStatsFromChart = () => {
        if (!chartInstance.current) return;
        const chart = chartInstance.current;
        const xScale = chart.scales.x;
        const filtered = getFilteredData(allData, currentTimeRange);
        const startIndex = Math.max(0, Math.floor(xScale.min));
        const endIndex = Math.min(filtered.length - 1, Math.ceil(xScale.max));
        const visibleData = filtered.slice(startIndex, endIndex + 1);
        if (visibleData.length > 0) setStats(calculateStats(visibleData));
    };

    const getFilteredData = (data, range) => {
        if (range === 'all') return data;
        const now = new Date();
        const cutoffDate = new Date();
        if (range === '3m') cutoffDate.setMonth(now.getMonth() - 3);
        else if (range === '6m') cutoffDate.setMonth(now.getMonth() - 6);
        else if (range === '1y') cutoffDate.setFullYear(now.getFullYear() - 1);
        return data.filter(item => new Date(item.date) >= cutoffDate);
    };

    const drawChart = (data) => {
        if (!chartRef.current) return;
        const ctx = chartRef.current.getContext('2d');
        if (chartInstance.current) chartInstance.current.destroy();
        // window.Chart is available via CDN
        const config = {
            type: 'bar',
            data: {
                datasets: [{
                    label: '差引（億円）',
                    data: data.map((d, index) => ({ x: index, y: d.balance })),
                    backgroundColor: (ctx) => (!ctx.parsed || ctx.parsed.y === undefined) ? 'rgba(74, 134, 232, 0.7)' : ctx.parsed.y >= 0 ? 'rgba(74, 134, 232, 0.7)' : 'rgba(230, 124, 115, 0.7)',
                    borderColor: (ctx) => (!ctx.parsed || ctx.parsed.y === undefined) ? '#4A86E8' : ctx.parsed.y >= 0 ? '#4A86E8' : '#E67C73',
                    borderWidth: 1,
                    barPercentage: 0.9,
                    categoryPercentage: 0.9
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'white',
                        titleColor: '#334155',
                        bodyColor: '#334155',
                        borderColor: '#e2e8f0',
                        borderWidth: 1,
                        padding: 12,
                        displayColors: false,
                        callbacks: {
                            title: (context) => data[Math.round(context[0].parsed.x)]?.tooltipDate || '',
                            label: (context) => {
                                const index = Math.round(context.parsed.x);
                                if (index >= 0 && index < data.length) {
                                    const val = data[index].balance;
                                    const raw = data[index].rawBalance;
                                    const sign = val >= 0 ? '+' : '';
                                    return `${sign}${formatNumber(val)}億円 (${sign}${(raw * 1000).toLocaleString('ja-JP')}円)`;
                                }
                                return '';
                            },
                            afterLabel: (context) => context.parsed.y >= 0 ? '買い越し' : '売り越し'
                        }
                    },
                    zoom: {
                        pan: { enabled: true, mode: 'x', threshold: 0 },
                        zoom: { wheel: { enabled: true, speed: 0.1 }, pinch: { enabled: true }, mode: 'x', onZoomComplete: updateStatsFromChart }
                    }
                },
                scales: {
                    y: { ticks: { callback: (value, index, ticks) => index === ticks.length - 1 ? formatNumber(value) + '億円' : formatNumber(value) }, grid: { color: '#e2e8f0' } },
                    x: { type: 'linear', min: 0, max: data.length - 1, ticks: { callback: (value) => data[Math.round(value)]?.displayDate || '', maxRotation: 45, minRotation: 45, autoSkip: true, maxTicksLimit: 20 }, grid: { color: '#e2e8f0' } }
                }
            }
        };
        // Use window.Chart because it's loaded via CDN script tag in index.html for chart.js
        chartInstance.current = new window.Chart(ctx, config);
    };

    useEffect(() => {
        const loadData = async () => {
            try {
                const res = await fetch('history.csv');
                const text = res.ok ? await res.text() : null;
                if (!text) throw new Error("CSV load failed");
                Papa.parse(text, {
                    header: true,
                    dynamicTyping: true,
                    skipEmptyLines: true,
                    complete: (results) => {
                        const raw = results.data.filter(r => r.date && r.balance != null).map(r => ({ date: r.date, balance: r.balance / 100000, rawBalance: r.balance })).sort((a, b) => new Date(a.date) - new Date(b.date));
                        const processed = calculateWeekLabels(raw);
                        setAllData(processed);
                        if (processed.length > 0) setLastUpdate(`最終更新: ${getFormattedReleaseDate(processed[processed.length - 1].date)}`);
                    }
                });
            } catch (e) { console.error(e); setLastUpdate("データの読み込みに失敗しました"); }
        };
        loadData();
        const interval = setInterval(loadData, 5 * 60 * 1000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (allData.length === 0) return;
        const filtered = getFilteredData(allData, currentTimeRange);
        setDataCount(filtered.length);
        drawChart(filtered);
        setStats(calculateStats(filtered));
    }, [allData, currentTimeRange]);

    return (
        <div className="space-y-6">
            <div className="gradient-bg text-white shadow-lg rounded-xl -mx-4 md:mx-0 p-6 md:p-8 mb-8 animate-fade-in-up">
                <h1 className="text-3xl md:text-4xl font-bold mb-2">JPX 海外投資家動向</h1>
                <p className="text-blue-100 text-sm mt-2">{lastUpdate}</p>
            </div>
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-6 animate-fade-in-up">
                <h2 className="text-xl font-bold text-slate-900 mb-4">差引推移 <span className="text-sm font-normal text-slate-500 ml-2">({dataCount}件のデータ)</span></h2>
                <div style={{ position: 'relative', height: '500px' }}>
                    <canvas ref={chartRef}></canvas>
                    <div style={{ position: 'absolute', bottom: '90px', left: '80px', display: 'flex', gap: '8px', zIndex: 10 }}>
                        <button onClick={() => zoomChart('in')} className="px-3 py-2 bg-white/90 backdrop-blur text-slate-700 rounded-lg shadow-md hover:bg-white transition-colors text-sm font-medium border border-slate-300">＋</button>
                        <button onClick={() => zoomChart('out')} className="px-3 py-2 bg-white/90 backdrop-blur text-slate-700 rounded-lg shadow-md hover:bg-white transition-colors text-sm font-medium border border-slate-300">ー</button>
                    </div>
                    <div style={{ position: 'absolute', bottom: '90px', right: '20px', display: 'flex', gap: '8px', zIndex: 10 }}>
                        <button onClick={() => panChart('left')} className="px-3 py-2 bg-white/90 backdrop-blur text-slate-700 rounded-lg shadow-md hover:bg-white transition-colors text-sm font-medium border border-slate-300">← 左へ</button>
                        <button onClick={() => panChart('right')} className="px-3 py-2 bg-white/90 backdrop-blur text-slate-700 rounded-lg shadow-md hover:bg-white transition-colors text-sm font-medium border border-slate-300">右へ →</button>
                    </div>
                </div>
                <div className="mt-4 pt-4 border-t border-slate-200"><p className="text-xs text-slate-500">💡 PC: ドラッグで左右移動、ホイール(縦)でズーム | スマホ: ピンチイン・アウトでズーム、スワイプで移動</p></div>
            </div>
            {stats && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6 mb-6 animate-fade-in-up">
                    {[
                        { label: '最新週（先週）の売買状況', value: stats.latest.balance, color: stats.latest.balance >= 0 ? 'text-blue-600' : 'text-red-500', sub: stats.latest.balance >= 0 ? '買い越し' : '売り越し' },
                        { label: '買い越し 平均', value: stats.positiveAvg, color: 'text-blue-600', sub: '表示範囲内' },
                        { label: '買い越し 中央値', value: stats.positiveMedian, color: 'text-blue-600', sub: '表示範囲内' },
                        { label: '売り越し 平均', value: stats.negativeAvg, color: 'text-red-500', sub: '表示範囲内' },
                        { label: '売り越し 中央値', value: stats.negativeMedian, color: 'text-red-500', sub: '表示範囲内' },
                    ].map((s, i) => (
                        <div key={i} className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                            <p className="text-slate-600 text-sm font-medium mb-2">{s.label}</p>
                            <p className={`text-3xl font-bold ${s.color}`}>{formatLargeNumber(s.value)}</p>
                            <p className="text-slate-400 text-xs mt-1">{s.sub}</p>
                        </div>
                    ))}
                </div>
            )}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4 animate-fade-in-up">
                <div className="flex flex-wrap gap-4 items-center">
                    <div className="flex items-center gap-2"><span className="text-slate-600 text-sm font-medium">期間:</span><div className="flex gap-1">{[{ v: 'all', l: '全期間' }, { v: '1y', l: '1年' }, { v: '6m', l: '6ヶ月' }, { v: '3m', l: '3ヶ月' }].map(opt => (<button key={opt.v} onClick={() => setCurrentTimeRange(opt.v)} className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${currentTimeRange === opt.v ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>{opt.l}</button>))}</div></div>
                    <button onClick={resetZoom} className="px-4 py-2 bg-slate-100 text-slate-600 rounded-lg hover:bg-slate-200 transition-colors text-sm font-medium">🔄 ズームリセット</button>
                </div>
            </div>
            <div className="mt-8 text-center text-slate-500 text-sm"><p>データソース: <a href="https://www.jpx.co.jp/markets/statistics-equities/investor-type/00-00-archives-00.html" target="_blank" className="text-blue-600 hover:underline">日本取引所グループ (JPX)</a></p></div>
        </div>
    );
};

export default ForeignInvestors;
