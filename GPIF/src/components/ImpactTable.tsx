import { LatestDrift } from '../types';

interface ImpactTableProps {
  latestDrift: LatestDrift | null;
  aum: number;
}

export function ImpactTable({ latestDrift, aum }: ImpactTableProps) {
  if (!latestDrift) {
    return <div className="p-4 text-slate-400 text-center font-medium">データがありません</div>;
  }

  const formatTrillions = (value: number) => {
    return value.toFixed(2) + '兆円';
  };

  const formatPercent = (value: number) => {
    return (value > 0 ? '+' : '') + value.toFixed(2) + '%';
  };

  const calculateImpact = (drift: number) => {
    // If drift is negative, it's underweighted, so we need to BUY (positive impact)
    // If drift is positive, it's overweighted, so we need to SELL (negative impact)
    return -drift / 100 * aum;
  };

  const rows = [
    { name: '国内株式 (TOPIX)', key: 'JP_EQ', color: 'text-[#7C4DFF]' },
    { name: '外国株式 (MSCI ACWI)', key: 'GL_EQ', color: 'text-[#F472B6]' },
    { name: '国内債券 (JGB)', key: 'JP_BD', color: 'text-[#475569]' },
    { name: '外国債券 (WGBI)', key: 'GL_BD', color: 'text-[#94a3b8]' },
  ];

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="w-full text-sm text-left text-slate-700">
        <thead className="text-xs uppercase bg-slate-50 font-bold text-slate-500">
          <tr>
            <th className="px-6 py-3">資産クラス</th>
            <th className="px-6 py-3 text-right">乖離率 (Drift)</th>
            <th className="px-6 py-3 text-right">インパクト（金額）</th>
            <th className="px-6 py-3 text-center">アクション</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => {
            const drift = latestDrift[row.key as keyof LatestDrift];
            const impact = calculateImpact(drift);
            const isBuy = impact > 0;

            return (
              <tr key={row.key} className="hover:bg-slate-50 transition-colors">
                <td className={`px-6 py-4 font-bold ${row.color}`}>
                  {row.name}
                </td>
                <td className="px-6 py-4 text-right font-mono font-bold">
                  {formatPercent(drift)}
                </td>
                <td className={`px-6 py-4 text-right font-mono font-bold ${isBuy ? 'text-emerald-500' : 'text-rose-500'}`}>
                  {isBuy ? '+' : ''}{formatTrillions(impact)}
                </td>
                <td className="px-6 py-4 text-center">
                  <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                    isBuy ? 'bg-emerald-100 text-emerald-600' : 'bg-rose-100 text-rose-600'
                  }`}>
                    {isBuy ? '買越 (BUY)' : '売越 (SELL)'}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
