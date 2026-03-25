import json
import pandas as pd

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
        out.append(f"売買フローエラー: {e}")

    # 2. オプション手口 (米系)
    try:
        with open('data/teguchi.json', 'r', encoding='utf-8') as f:
            teguchi = json.load(f)
        out.append(f"\n【日経225オプション米系手口】")
        for m in teguchi.get('matrix', []):
            name = m.get('Company', '')
            if any(x in name for x in ['ゴールドマン', 'モルガン']):
                out.append(f"{name}: Call={m.get('C_Total',0)}, Put={m.get('P_Total',0)}")
                # find major strikes
                strikes = []
                for k, v in m.items():
                    if k.startswith('C_') and k != 'C_Total' and v > 200:
                        strikes.append(f"{k}({v})")
                    if k.startswith('P_') and k != 'P_Total' and v > 200:
                        strikes.append(f"{k}({v})")
                if strikes: out.append(f"  -> 主要建玉: " + ", ".join(strikes))
                
        with open('data/option_history.json', 'r', encoding='utf-8') as f:
            opt = json.load(f)
        out.append(f"\n【全体OP建玉残高(OI) トップ3】")
        calls = sorted(opt.get('call', []), key=lambda x: x.get('oi', 0), reverse=True)[:3]
        puts = sorted(opt.get('put', []), key=lambda x: x.get('oi', 0), reverse=True)[:3]
        out.append(f"Call: " + ", ".join([f"{c['strike']}円({c['oi']}枚)" for c in calls]))
        out.append(f"Put: " + ", ".join([f"{p['strike']}円({p['oi']}枚)" for p in puts]))
    except Exception as e:
        out.append(f"OPエラー: {e}")

    # 3. セクター & US動向 (Intraday)
    try:
        with open('data/etf_intraday.json', 'r', encoding='utf-8') as f:
            ei = json.load(f)
        out.append(f"\n【US指数 ＆ 個別・セクター】")
        prices = ei.get('prices', {})
        def calc_perf(sym):
            series = prices.get(sym)
            if not series or len(series) < 2: return 0.0
            return (series[-1] / series[0] - 1) * 100 if series[0] else 0.0 # vs day open or first data

        for sym in ['^NDX', '^GSPC', '^SOX', '^DJI', '^N225', '1306.T']:
            out.append(f"{sym}: {calc_perf(sym):.2f}%")

        topix100 = ei.get('topix100', {})
        t100_perf = [(name, calc_perf(sym)) for sym, name in topix100.items() if sym in prices]
        t100_perf.sort(key=lambda x: x[1], reverse=True)
        out.append(f"\n【TOPIX100 上位5銘柄】: " + ", ".join([f"{n}({p:.2f}%)" for n, p in t100_perf[:5]]))
        out.append(f"【TOPIX100 下位5銘柄】: " + ", ".join([f"{n}({p:.2f}%)" for n, p in t100_perf[-5:]]))

        semi = ei.get('semiconductor_jp', {})
        semi_perf = [(name, calc_perf(sym)) for sym, name in semi.items() if sym in prices]
        semi_perf.sort(key=lambda x: x[1], reverse=True)
        out.append(f"【半導体銘柄 トップ3】: " + ", ".join([f"{n}({p:.2f}%)" for n, p in semi_perf[:3]]))
        
        sectors = ei.get('sectors', {})
        sec_perf = [(name, calc_perf(sym)) for sym, name in sectors.items() if sym in prices and not str(sym).startswith('^')]
        sec_perf.sort(key=lambda x: x[1], reverse=True)
        out.append(f"\n【主要セクター】")
        out.append(f"上位3: " + ", ".join([f"{n}({p:.2f}%)" for n, p in sec_perf[:3]]))
        out.append(f"下位3: " + ", ".join([f"{n}({p:.2f}%)" for n, p in sec_perf[-3:]]))

    except Exception as e:
        out.append(f"イントラデイエラー: {e}")

    print("\n".join(out))

if __name__ == "__main__":
    summarize()
