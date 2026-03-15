import { MarketData, DriftDataPoint, LatestDrift } from './types';

export function calculateDrift(
  data: MarketData,
  lookbackDays: number
): { chartData: DriftDataPoint[]; latestDrift: LatestDrift | null } {
  if (!data.JP_EQ || !data.JP_BD || !data.GL_EQ || !data.GL_BD) {
    return { chartData: [], latestDrift: null };
  }

  // Find common dates
  const jpEqDates = new Set(data.JP_EQ.map(d => d.date));
  const jpBdDates = new Set(data.JP_BD.map(d => d.date));
  const glEqDates = new Set(data.GL_EQ.map(d => d.date));
  const glBdDates = new Set(data.GL_BD.map(d => d.date));

  const commonDates = [...jpEqDates]
    .filter(d => jpBdDates.has(d) && glEqDates.has(d) && glBdDates.has(d))
    .sort();

  if (commonDates.length === 0) return { chartData: [], latestDrift: null };

  // We want to use the date `lookbackDays` ago as the base.
  // If we don't have exactly that many trading days, we just take the last N common dates.
  const targetDays = Math.min(lookbackDays, commonDates.length - 1);
  const startIndex = Math.max(0, commonDates.length - 1 - targetDays);
  const baseDate = commonDates[startIndex];

  const getBasePrice = (series: any[], date: string) => {
    const point = series.find(d => d.date === date);
    return point ? point.close : null;
  };

  const basePrices = {
    JP_EQ: getBasePrice(data.JP_EQ, baseDate),
    JP_BD: getBasePrice(data.JP_BD, baseDate),
    GL_EQ: getBasePrice(data.GL_EQ, baseDate),
    GL_BD: getBasePrice(data.GL_BD, baseDate),
  };

  if (!basePrices.JP_EQ || !basePrices.JP_BD || !basePrices.GL_EQ || !basePrices.GL_BD) {
    return { chartData: [], latestDrift: null };
  }

  const chartData: DriftDataPoint[] = [];
  let latestDrift: LatestDrift | null = null;

  for (let i = startIndex; i < commonDates.length; i++) {
    const date = commonDates[i];
    
    const getPrice = (series: any[]) => series.find(d => d.date === date)?.close || 0;
    
    const prices = {
      JP_EQ: getPrice(data.JP_EQ),
      JP_BD: getPrice(data.JP_BD),
      GL_EQ: getPrice(data.GL_EQ),
      GL_BD: getPrice(data.GL_BD),
    };

    const returns = {
      JP_EQ: (prices.JP_EQ / basePrices.JP_EQ - 1) * 100,
      JP_BD: (prices.JP_BD / basePrices.JP_BD - 1) * 100,
      GL_EQ: (prices.GL_EQ / basePrices.GL_EQ - 1) * 100,
      GL_BD: (prices.GL_BD / basePrices.GL_BD - 1) * 100,
    };

    const portfolioAvg = (returns.JP_EQ + returns.JP_BD + returns.GL_EQ + returns.GL_BD) / 4;

    const drift = {
      JP_EQ: returns.JP_EQ - portfolioAvg,
      JP_BD: returns.JP_BD - portfolioAvg,
      GL_EQ: returns.GL_EQ - portfolioAvg,
      GL_BD: returns.GL_BD - portfolioAvg,
    };

    chartData.push({
      time: date,
      ...drift
    });

    if (i === commonDates.length - 1) {
      latestDrift = drift;
    }
  }

  return { chartData, latestDrift };
}
