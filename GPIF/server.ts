import express from 'express';
import { createServer as createViteServer } from 'vite';
import path from 'path';
import YahooFinance from 'yahoo-finance2';
import { subDays, format } from 'date-fns';

const yahooFinance = new YahooFinance();

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json());

  // API routes FIRST
  app.get('/api/market-data', async (req, res) => {
    try {
      const lookbackDays = parseInt(req.query.lookback as string) || 90;
      
      // Tickers
      // JP_EQ: NEXT FUNDS TOPIX ETF (1306.T)
      // JP_BD: NEXT FUNDS Nomura BPI Comprehensive ETF (2510.T)
      // GL_EQ: MAXIS All Country Equity ETF (2559.T)
      // GL_BD: NEXT FUNDS Foreign Bond FTSE WGBI ETF (2511.T)
      
      const tickers = {
        JP_EQ: '1306.T',
        JP_BD: '2510.T',
        GL_EQ: '2559.T',
        GL_BD: '2511.T'
      };

      // We need to fetch data from (lookbackDays + 20) days ago to ensure we have enough trading days
      const startDate = subDays(new Date(), lookbackDays + 30);

      const results: Record<string, any[]> = {};

      for (const [key, symbol] of Object.entries(tickers)) {
        const queryOptions = { period1: startDate, interval: '1d' as const };
        const result = await yahooFinance.chart(symbol, queryOptions);
        results[key] = result.quotes
          .filter(r => r.close !== null && r.close !== undefined)
          .map(r => ({
            date: format(r.date, 'yyyy-MM-dd'),
            close: r.close
          }));
      }

      res.json(results);
    } catch (error) {
      console.error('Error fetching market data:', error);
      res.status(500).json({ error: error instanceof Error ? error.message : 'Failed to fetch market data' });
    }
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
