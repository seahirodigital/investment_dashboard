import { useState, useEffect } from 'react';
import { RefreshCw, HelpCircle, X } from 'lucide-react';
import { Chart } from './components/Chart';
import { ImpactTable } from './components/ImpactTable';
import { calculateDrift } from './utils';
import { MarketData, DriftDataPoint, LatestDrift } from './types';

const lookbackOptions = [
  { value: '1', label: '1日' },
  { value: '2', label: '2日' },
  { value: '3', label: '3日' },
  { value: '4', label: '4日' },
  { value: '5', label: '5日' },
  { value: '6', label: '6日' },
  { value: '7', label: '7日' },
  { value: '8', label: '8日' },
  { value: '9', label: '9日' },
  { value: '10', label: '10日' },
  { value: '14', label: '2週間' },
  { value: '30', label: '1ヶ月' },
  { value: '60', label: '2ヶ月' },
  { value: '90', label: '3ヶ月' },
  { value: '120', label: '4ヶ月' },
  { value: '150', label: '5ヶ月' },
  { value: '180', label: '半年' },
  { value: '365', label: '1年' },
  { value: '730', label: '2年' },
  { value: '1095', label: '3年' },
];

export default function App() {
  const [showInfoModal, setShowInfoModal] = useState<boolean>(false);
  const [lookbackDaysInput, setLookbackDaysInput] = useState<string>('7');
  const [aumInput, setAumInput] = useState<string>('250'); // 250 Trillion JPY
  
  const [marketData, setMarketData] = useState<MarketData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [chartData, setChartData] = useState<DriftDataPoint[]>([]);
  const [latestDrift, setLatestDrift] = useState<LatestDrift | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const lookbackDays = parseInt(lookbackDaysInput) || 7;
      // Fetch pre-generated data from static JSON instead of node backend
      const response = await fetch('../../data/gpif_data.json');
      if (!response.ok) {
        throw new Error('マーケットデータの取得に失敗しました');
      }
      const fullData = await response.json();
      
      // Filter the full data by lookbackDays locally (+30 days overlap like original API)
      const cutoffDate = new Date();
      cutoffDate.setDate(cutoffDate.getDate() - (lookbackDays + 30));
      const cutoffStr = cutoffDate.toISOString().split('T')[0];
      
      const filteredData = {} as MarketData;
      for (const [key, records] of Object.entries(fullData)) {
        filteredData[key as keyof MarketData] = (records as any[]).filter(r => r.date >= cutoffStr);
      }
      
      setMarketData(filteredData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'エラーが発生しました');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []); // Only run on mount, manual refresh triggers later

  useEffect(() => {
    if (marketData) {
      const lookbackDays = parseInt(lookbackDaysInput) || 7;
      const { chartData, latestDrift } = calculateDrift(marketData, lookbackDays);
      setChartData(chartData);
      setLatestDrift(latestDrift);
    }
  }, [marketData, lookbackDaysInput]);

  const handleRefresh = () => {
    fetchData();
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-700 font-sans selection:bg-[#7C4DFF]/30">
      {/* Header (header-hp 統一スタイル) */}
      <header className="border-b border-slate-200 bg-white sticky top-0 z-10" style={{ boxShadow: '0 2px 4px rgba(0,0,0,0.05)' }}>
        <div className="max-w-7xl mx-auto px-6 py-3 flex flex-col md:flex-row items-center justify-between gap-3 md:gap-0">
          <div className="flex items-center gap-3 w-full md:w-auto">
            <h1 className="text-xs font-bold text-[#7C4DFF]">GPIF分析</h1>
            <span className="text-slate-400 text-xs font-medium ml-2">運用資産配分 / リバランスインパクト推定</span>
          </div>

          <div className="flex items-center gap-4 text-xs w-full md:w-auto justify-end overflow-x-auto">
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-slate-500 font-bold shrink-0">期間:</span>
              <select
                value={lookbackDaysInput}
                onChange={(e) => setLookbackDaysInput(e.target.value)}
                className="bg-white border border-slate-200 rounded px-2 py-0.5 text-slate-700 focus:outline-none focus:border-[#7C4DFF]"
              >
                {lookbackOptions.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <span className="text-slate-500 font-bold shrink-0">運用資産:</span>
              <div className="flex items-center">
                <input
                  type="text"
                  value={aumInput}
                  onChange={(e) => setAumInput(e.target.value)}
                  className="bg-white border border-slate-200 rounded px-2 py-0.5 text-slate-700 w-14 text-right focus:outline-none focus:border-[#7C4DFF] font-mono"
                />
                <span className="ml-1 text-slate-500">兆円</span>
              </div>
            </div>

            <button
              onClick={handleRefresh}
              disabled={loading}
              className="flex items-center gap-2 bg-[#7C4DFF] hover:bg-[#651FFF] text-white font-bold px-3 py-1 rounded transition-colors shadow-sm disabled:opacity-50 shrink-0"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>更新</span>
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {error && (
          <div className="bg-rose-50 border border-rose-200 text-rose-500 px-4 py-3 rounded-lg text-sm font-medium">
            {error}
          </div>
        )}

        {/* Chart Section */}
        <section className="bg-white border border-slate-200 rounded-xl p-6 space-y-4 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-500">GPIFバランス</h2>
            <div className="flex items-center gap-4 text-xs font-bold text-slate-600">
              <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-[#7C4DFF]"></div> 国内株式</div>
              <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-[#F472B6]"></div> 外国株式</div>
              <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-[#475569]"></div> 国内債券</div>
              <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-[#94a3b8]"></div> 外国債券</div>
            </div>
          </div>
          
          {loading && chartData.length === 0 ? (
            <div className="w-full h-[400px] flex items-center justify-center border border-slate-200 rounded-xl bg-slate-50">
              <RefreshCw className="w-6 h-6 text-slate-400 animate-spin" />
            </div>
          ) : (
            <Chart data={chartData} />
          )}
        </section>

        {/* Table Section */}
        <section className="bg-white border border-slate-200 rounded-xl p-6 space-y-4 shadow-sm">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-bold text-slate-500">リバランスインパクト</h2>
            <button
              onClick={() => setShowInfoModal(true)}
              className="text-slate-300 hover:text-[#7C4DFF] transition-colors"
            >
              <HelpCircle className="w-4 h-4" />
            </button>
          </div>
          <ImpactTable latestDrift={latestDrift} aum={parseInt(aumInput) || 250} />
        </section>
      </main>

      {/* リバランスインパクト説明モーダル */}
      {showInfoModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={() => setShowInfoModal(false)}
        >
          <div
            className="bg-white rounded-xl p-6 w-[90%] max-w-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-base font-bold text-slate-800 flex items-center gap-2">
                <HelpCircle className="w-4 h-4 text-[#7C4DFF]" />
                リバランスの仕組み
              </h3>
              <button
                onClick={() => setShowInfoModal(false)}
                className="text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="text-sm text-slate-600 space-y-4">
              <div>
                <p className="font-bold mb-1 text-[#7C4DFF]">「乖離許容幅」という公式ルール</p>
                <p className="mb-2">GPIFには、各資産ごとに「ここまではズレてもOK」という<strong>乖離許容幅</strong>が設定されています。2025年度からの第5期中期計画では以下のようになっています。</p>
                <table className="w-full mb-2 border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50">
                      <th className="text-left py-1.5 px-2 font-medium text-slate-500">資産クラス</th>
                      <th className="text-left py-1.5 px-2 font-medium text-slate-500">基本構成割合</th>
                      <th className="text-left py-1.5 px-2 font-medium text-slate-500">乖離許容幅</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    <tr><td className="py-1.5 px-2">国内株式</td><td className="py-1.5 px-2">25%</td><td className="py-1.5 px-2">±6% (19.0%〜31.0%)</td></tr>
                    <tr><td className="py-1.5 px-2">外国株式</td><td className="py-1.5 px-2">25%</td><td className="py-1.5 px-2">±6% (19.0%〜31.0%)</td></tr>
                    <tr><td className="py-1.5 px-2">国内債券</td><td className="py-1.5 px-2">25%</td><td className="py-1.5 px-2">±6% (19.0%〜31.0%)</td></tr>
                    <tr><td className="py-1.5 px-2">外国債券</td><td className="py-1.5 px-2">25%</td><td className="py-1.5 px-2">±5% (20.0%〜30.0%)</td></tr>
                  </tbody>
                </table>
                <p>日本株が1週間で少しアウトパフォームして比率が26%になっても、許容幅（31.0%まで）の中に収まっていれば、「直ちに売る義務」は生じません。</p>
              </div>
              <div>
                <p className="font-bold mb-1 text-[#7C4DFF]">リバランスの「トリガー」と「手段」</p>
                <ul className="list-disc pl-4 space-y-1.5">
                  <li><strong>乖離が限界に近づいたとき:</strong> ±5〜6%に近づくと、計画的に売買が検討されます。</li>
                  <li><strong>先物での調整:</strong> 株価指数先物を売却し、実質的な比率を素早く調整します。</li>
                  <li><strong>配当金・利子の再投資:</strong> 比率が下がっている資産の購入に充て、現物を売らずに調整します。</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
