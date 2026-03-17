import { useState, useEffect } from 'react';
import { Activity, RefreshCw, Info } from 'lucide-react';
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
      {/* Header */}
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur-md sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 sm:py-0 sm:h-16 flex flex-col sm:flex-row items-center justify-between gap-4 sm:gap-0">
          <div className="flex items-center gap-3 w-full sm:w-auto justify-between sm:justify-start">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-r from-[#7C4DFF] to-[#651FFF] flex items-center justify-center shadow-sm">
                <Activity className="w-5 h-5 text-white" />
              </div>
              <h1 className="font-bold text-lg text-slate-800 tracking-tight">GPIF分析</h1>
            </div>
          </div>

          <div className="flex items-center gap-4 text-sm w-full sm:w-auto justify-between sm:justify-end overflow-x-auto pb-1 sm:pb-0">
            <div className="flex items-center gap-2 shrink-0">
              <label className="font-bold text-slate-500">期間</label>
              <select
                value={lookbackDaysInput}
                onChange={(e) => setLookbackDaysInput(e.target.value)}
                className="bg-white border border-slate-200 rounded-lg px-2 py-1.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-[#7C4DFF]/50 font-medium cursor-pointer"
              >
                {lookbackOptions.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <label className="font-bold text-slate-500">運用資産</label>
              <div className="flex items-center">
                <input
                  type="text"
                  value={aumInput}
                  onChange={(e) => setAumInput(e.target.value)}
                  className="bg-white border border-slate-200 rounded-lg px-2 py-1.5 text-slate-800 w-16 text-right focus:outline-none focus:ring-2 focus:ring-[#7C4DFF]/50 font-mono"
                />
                <span className="ml-1 text-slate-500 font-bold">兆円</span>
              </div>
            </div>

            <button
              onClick={handleRefresh}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#7C4DFF] hover:bg-[#651FFF] text-white font-bold transition-colors shadow-sm disabled:opacity-50 shrink-0"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">更新</span>
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
            <div className="relative group">
              <Info className="w-4 h-4 text-slate-400 cursor-help" />
              <div className="absolute left-[-1rem] sm:left-0 bottom-full mb-2 hidden group-hover:block w-[calc(100vw-2rem)] sm:w-[480px] p-4 bg-slate-800 text-white text-xs rounded-lg shadow-xl z-50 leading-relaxed">
                <p className="font-bold mb-1 text-sm text-[#7C4DFF]">2. 「乖離許容幅」という公式ルール</p>
                <p className="mb-2 text-slate-300">GPIFには、各資産ごとに「ここまではズレてもOK」という<strong>乖離許容幅（かいりきょようはば）</strong>が設定されています。2025年度からの第5期中期計画では以下のようになっています。</p>
                <table className="w-full mb-2 border-collapse text-slate-300">
                  <thead>
                    <tr className="border-b border-slate-600">
                      <th className="text-left py-1 font-medium">資産クラス</th>
                      <th className="text-left py-1 font-medium">基本構成割合</th>
                      <th className="text-left py-1 font-medium">乖離許容幅</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/50">
                    <tr><td className="py-1">国内株式</td><td>25%</td><td>±6% (19.0% ～ 31.0%)</td></tr>
                    <tr><td className="py-1">外国株式</td><td>25%</td><td>±6% (19.0% ～ 31.0%)</td></tr>
                    <tr><td className="py-1">国内債券</td><td>25%</td><td>±6% (19.0% ～ 31.0%)</td></tr>
                    <tr><td className="py-1">外国債券</td><td>25%</td><td>±5% (20.0% ～ 30.0%)</td></tr>
                  </tbody>
                </table>
                <p className="mb-4 text-slate-300">つまり、日本株が1週間で少しアウトパフォームして比率が26%になったとしても、許容幅（31.0%まで）の中に収まっていれば、「直ちに売る義務」は生じません。</p>

                <p className="font-bold mb-1 text-sm text-[#7C4DFF]">3. リバランスの「トリガー」と「手段」</p>
                <p className="mb-2 text-slate-300">では、いつ売るのか？ 実際には以下のタイミングや手法が使われます。</p>
                <ul className="list-disc pl-4 space-y-1.5 text-slate-300">
                  <li><strong className="text-white">乖離が限界に近づいたとき:</strong> 上記の±5〜6%に近づくと、アラートが鳴り、計画的に売買が検討されます。</li>
                  <li><strong className="text-white">先物（さきもの）での調整:</strong> 現物株を売ると時間がかかるため、株価指数先物を売却することで、一時的に「実質的な比率」を25%に引き戻すテクニックを多用します。</li>
                  <li><strong className="text-white">配当金や利子の再投資:</strong> 株式から出た配当金を、比率が下がっている債券の購入に充てることで、現物を売らずに比率を整える「自然なリバランス」も行っています。</li>
                </ul>
              </div>
            </div>
          </div>
          <ImpactTable latestDrift={latestDrift} aum={parseInt(aumInput) || 250} />
        </section>
      </main>
    </div>
  );
}
