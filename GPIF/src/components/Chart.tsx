import { useEffect, useRef } from 'react';
import { createChart, ColorType, ISeriesApi, LineData, IChartApi, LineSeries } from 'lightweight-charts';
import { DriftDataPoint } from '../types';

interface ChartProps {
  data: DriftDataPoint[];
}

export function Chart({ data }: ChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<Record<string, { right: ISeriesApi<"Line">, left: ISeriesApi<"Line"> }>>({});
  const zeroSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#64748b',
      },
      grid: {
        vertLines: { color: '#f1f5f9' },
        horzLines: { color: '#f1f5f9' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 400,
      crosshair: {
        mode: 1,
      },
      timeScale: {
        borderColor: '#e2e8f0',
      },
      rightPriceScale: {
        visible: true,
        borderColor: '#e2e8f0',
      },
      leftPriceScale: {
        visible: true,
        borderColor: 'transparent',
        textColor: 'transparent', // 軸の数値を透明にして隠す
      },
    });
    
    chartRef.current = chart;

    // Zero-Axis Line
    zeroSeriesRef.current = chart.addSeries(LineSeries, {
      color: '#94a3b8',
      lineWidth: 1,
      lineStyle: 2, // Dashed
      crosshairMarkerVisible: false,
      priceLineVisible: false,
      lastValueVisible: false,
      priceScaleId: 'right',
    });

    // 右軸用（線と数値のみ）と左軸用（凡例ラベルのみ）の2つのシリーズを作成
    const addDualSeries = (key: string, color: string, title: string) => {
      const right = chart.addSeries(LineSeries, { 
        color, 
        lineWidth: 2, 
        priceScaleId: 'right' 
      });
      
      const left = chart.addSeries(LineSeries, { 
        color, 
        lineVisible: false, // 線は描画しない
        crosshairMarkerVisible: false, 
        priceLineVisible: false,
        priceScaleId: 'left',
        title // 左軸にのみタイトル（凡例）を表示
      });

      seriesRefs.current[key] = { right, left };
    };

    addDualSeries('JP_EQ', '#7C4DFF', '国内株式');
    addDualSeries('GL_EQ', '#F472B6', '外国株式');
    addDualSeries('JP_BD', '#475569', '国内債券');
    addDualSeries('GL_BD', '#94a3b8', '外国債券');

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current || data.length === 0) return;

    const mapData = (key: keyof DriftDataPoint) => 
      data.map(d => ({ time: d.time, value: d[key] as number } as LineData));

    if (zeroSeriesRef.current) {
      zeroSeriesRef.current.setData(data.map(d => ({ time: d.time, value: 0 } as LineData)));
    }

    const updateDualSeries = (key: string) => {
      const mapped = mapData(key as keyof DriftDataPoint);
      if (seriesRefs.current[key]) {
        seriesRefs.current[key].right.setData(mapped);
        seriesRefs.current[key].left.setData(mapped);
      }
    };

    updateDualSeries('JP_EQ');
    updateDualSeries('GL_EQ');
    updateDualSeries('JP_BD');
    updateDualSeries('GL_BD');

    chartRef.current.timeScale().fitContent();
  }, [data]);

  return <div ref={chartContainerRef} className="w-full h-[400px] rounded-xl overflow-hidden border border-slate-200" />;
}
