import json
import pandas as pd
import os

def summarize():
    out = []
    
    # 1. 売買フロー
    try:
        with open('data/short_selling.json', 'r', encoding='utf-8') as f:
            ss_data = json.load(f)['data']
        ss_df = pd.DataFrame(ss_data).sort_values('date').tail(21)
        latest = ss_df.iloc[-1]
        ma20 = ss_df['total'].rolling(20).mean().iloc[-1]
        peak = ss_df['karauri_ratio'].rolling(20).max().iloc[-1]
        s1 = latest['total'] >= ma20 * 1.3
        s2 = latest['karauri_ratio'] <= peak * 0.8
        phase = 3 if s1 and s2 else (2 if s1 or s2 else 1)
        out.append(f"【売買フロー】")
        out.append(f"日付: {latest['date']}")
        out.append(f"売買代金: {latest['total']/1e6:.2f}兆 (20日MA: {ma20/1e6:.2f}兆) -> S1膨張: {s1}")
        out.append(f"空売り比率: {latest['karauri_ratio']*100:.1f}% (20日Peak: {peak*100:.1f}%) -> S2低下: {s2}")
        out.append(f"判定Phase: {phase}")
    except Exception as e:
        pass

    # 2. オプション手口 (米系)
    try:
        with open('data/teguchi.json', 'r', encoding='utf-8') as f:
            teguchi = json.load(f)
        teg_date = teguchi.get('date', '不明')
        out.append(f"\n【オプション手口 (日付: {teg_date})】")
        for m in teguchi.get('matrix', []):
            name = m.get('Company', '')
            if any(x in name for x in ['ゴールドマン', 'モルガン']):
                out.append(f"{name}: Call={m.get('C_Total',0)}, Put={m.get('P_Total',0)}")
                strikes = []
                for k, v in m.items():
                    if k.startswith('C_') and k != 'C_Total' and v > 200:
                        strikes.append(f"{k}({v})")
                    if k.startswith('P_') and k != 'P_Total' and v > 200:
                        strikes.append(f"{k}({v})")
                if strikes: out.append(f"  -> 主要建玉: " + ", ".join(strikes))
    except Exception as e:
        pass

    # 3. Daily Analysis (1 day) using etf_data.json
    try:
        with open('data/etf_data.json', 'r', encoding='utf-8') as f:
            ed = json.load(f)
        prices_daily = ed.get('prices', {})
        ds = ed.get('dates', [])
        latest_date = ds[-1] if ds else "不明"
        
        def calc_perf(sym):
            series = prices_daily.get(sym)
            if not series or len(series) < 2: return 0.0
            day1 = series[-2]
            day2 = series[-1]
            if day1 == 0: return 0.0
            return (day2 / day1 - 1) * 100
            
        out.append(f"\n【インデックス (日付: {latest_date})】")
        for sym in ['NQM26.CME', 'ESM26.CME', 'YMM26.CBT', '^N225', '1306.T', '2644.T']:
            out.append(f"{sym}: {calc_perf(sym):.2f}%")
            
        out.append(f"\n【セクター】")
        sectors = ed.get('sectors', {})
        sec_perf = [(name, calc_perf(sym)) for sym, name in sectors.items() if sym in prices_daily and not str(sym).startswith('^')]
        sec_perf.sort(key=lambda x: x[1], reverse=True)
        out.append(f"上位3: " + ", ".join([f"{n}({p:.2f}%)" for n, p in sec_perf[:3]]))
        out.append(f"下位3: " + ", ".join([f"{n}({p:.2f}%)" for n, p in sec_perf[-3:]]))
        
        out.append(f"\n【TOPIX100 Rankings】")
        topix100 = ed.get('topix100', {})
        t100_perf = [(name, calc_perf(sym)) for sym, name in topix100.items() if sym in prices_daily]
        t100_perf.sort(key=lambda x: x[1], reverse=True)
        out.append(f"=== TOP 20 ===")
        for i, (n, p) in enumerate(t100_perf[:20]):
            out.append(f"{i+1}. {n}({p:.2f}%)")
        out.append(f"=== BOTTOM 20 ===")
        for i, (n, p) in enumerate(t100_perf[-20:]):
            out.append(f"{i+1}. {n}({p:.2f}%)")

    except Exception as e:
        out.append(f"daily error: {e}")

    os.makedirs('market_analysis/reports', exist_ok=True)
    with open('market_analysis/reports/tmp_out.txt', 'w', encoding='utf-8') as f:
        f.write("\n".join(out))

if __name__ == "__main__":
    summarize()
