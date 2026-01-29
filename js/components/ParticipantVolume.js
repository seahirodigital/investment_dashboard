import React, { useState, useEffect } from 'react';

const ParticipantVolume = () => {
    const [data, setData] = useState(null);
    const [session, setSession] = useState('night'); // 'night' or 'day'
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const res = await fetch('./data/daily_participant.json');
                if (res.ok) {
                    const json = await res.json();
                    setData(json);
                } else {
                    console.warn("Daily participant data not found.");
                }
            } catch (e) {
                console.error(e);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    if (loading) return <div className="p-8 text-center text-slate-500">データを読み込み中...</div>;
    if (!data) return <div className="p-8 text-center text-red-500 bg-red-50 rounded-lg">最新の手口データが見つかりませんでした。<br/>平日20時以降に更新されます。</div>;

    const targetData = session === 'night' ? data.night_session : data.day_session;
    const sessionLabel = session === 'night' ? 'ナイト・セッション (立会)' : '日中取引 (立会)';

    const categoryColors = {
        'US': 'bg-blue-100 text-blue-800 border-blue-200',
        'EU': 'bg-green-100 text-green-800 border-green-200',
        'JP': 'bg-orange-100 text-orange-800 border-orange-200',
        'NET': 'bg-purple-100 text-purple-800 border-purple-200',
        'OTHERS': 'bg-slate-100 text-slate-800 border-slate-200'
    };

    const grouped = targetData.reduce((acc, item) => {
        const cat = item.category || 'OTHERS';
        if (!acc[cat]) acc[cat] = [];
        acc[cat].push(item);
        return acc;
    }, {});

    const categories = ['US', 'EU', 'JP', 'NET', 'OTHERS'];

    return (
        <div className="space-y-6">
            <div className="gradient-bg text-white shadow-lg rounded-xl p-6 md:p-8 animate-fade-in-up">
                <h1 className="text-3xl font-bold mb-2">取引参加者別取引高 (手口上位)</h1>
                <p className="text-blue-100 text-sm">データ日付: {data.date} (最終更新: {data.updated_at})</p>
            </div>

            <div className="flex space-x-2 bg-white p-2 rounded-lg shadow-sm border border-slate-200 w-fit">
                <button 
                    onClick={() => setSession('night')}
                    className={`px-4 py-2 rounded-md text-sm font-bold transition-all ${session === 'night' ? 'bg-slate-800 text-white shadow' : 'text-slate-500 hover:bg-slate-100'}`}
                >
                    🌙 ナイト・セッション
                </button>
                <button 
                    onClick={() => setSession('day')}
                    className={`px-4 py-2 rounded-md text-sm font-bold transition-all ${session === 'day' ? 'bg-slate-800 text-white shadow' : 'text-slate-500 hover:bg-slate-100'}`}
                >
                    ☀️ 日中取引
                </button>
            </div>

            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 animate-fade-in-up">
                <h2 className="text-xl font-bold text-slate-800 mb-4">{sessionLabel}</h2>
                {targetData.length === 0 ? (
                    <p className="text-slate-500">このセッションのデータはありません。</p>
                ) : (
                    <div className="space-y-8">
                        {categories.map(cat => {
                            if (!grouped[cat]) return null;
                            return (
                                <div key={cat} className="border border-slate-200 rounded-lg overflow-hidden">
                                    <div className={`px-4 py-2 font-bold text-sm border-b ${categoryColors[cat]}`}>
                                        {cat === 'US' && '🇺🇸 米系証券'}
                                        {cat === 'EU' && '🇪🇺 欧州系証券'}
                                        {cat === 'JP' && '🇯🇵 日系証券'}
                                        {cat === 'NET' && '🌐 ネット証券'}
                                        {cat === 'OTHERS' && 'その他'}
                                    </div>
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-sm text-left">
                                            <thead className="bg-slate-5 text-slate-500 border-b border-slate-200">
                                                <tr>
                                                    <th className="px-4 py-2 w-48">証券会社</th>
                                                    {Object.keys(grouped[cat][0].data).map(key => (
                                                        <th key={key} className="px-4 py-2 text-right whitespace-nowrap">{key}</th>
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-slate-100">
                                                {grouped[cat].map((item, idx) => (
                                                    <tr key={idx} className="hover:bg-slate-50">
                                                        <td className="px-4 py-2 font-medium text-slate-700">{item.name}</td>
                                                        {Object.entries(item.data).map(([k, val], i) => (
                                                            <td key={i} className="px-4 py-2 text-right font-mono">
                                                                {val.toLocaleString()}
                                                            </td>
                                                        ))}
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
                <div className="mt-4 text-right text-xs text-slate-400">
                ※JPX公表のExcelファイルより自動取得・集計。単位: 枚 (または金額)。
            </div>
        </div>
    );
};

export default ParticipantVolume;
