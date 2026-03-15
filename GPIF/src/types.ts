export interface MarketDataPoint {
  date: string;
  close: number;
}

export interface MarketData {
  JP_EQ: MarketDataPoint[];
  JP_BD: MarketDataPoint[];
  GL_EQ: MarketDataPoint[];
  GL_BD: MarketDataPoint[];
}

export interface DriftDataPoint {
  time: string;
  JP_EQ: number;
  JP_BD: number;
  GL_EQ: number;
  GL_BD: number;
}

export interface LatestDrift {
  JP_EQ: number;
  JP_BD: number;
  GL_EQ: number;
  GL_BD: number;
}
