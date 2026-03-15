import YahooFinance from 'yahoo-finance2';
import { subDays, format } from 'date-fns';

const yahooFinance = new YahooFinance();

async function test() {
  try {
    const lookbackDays = 90;
    const tickers = {
      JP_EQ: '1306.T',
      JP_BD: '2510.T',
      GL_EQ: '2559.T',
      GL_BD: '2511.T'
    };

    const startDate = subDays(new Date(), lookbackDays + 30);
    const period1 = format(startDate, 'yyyy-MM-dd');

    for (const [key, symbol] of Object.entries(tickers)) {
      console.log(`Fetching ${symbol}...`);
      const queryOptions = { period1: startDate, interval: '1d' as const };
      const result = await yahooFinance.chart(symbol, queryOptions);
      console.log(`Got ${result.quotes.length} records for ${symbol}`);
    }
  } catch (error) {
    console.error('Error:', error);
  }
}

test();
