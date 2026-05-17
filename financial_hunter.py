import pandas as pd
import os
import sys
from data_fetcher import FinDataFetcher
from strategies import StockStrategy
from notifier import TelegramNotifier
from datetime import datetime
from sync_utils import auto_sync_to_reg_hunter

# --- 關閉 FinMind 的干擾訊息 ---
from loguru import logger
logger.remove() 
logger.add(sys.stderr, level="WARNING")

# --- 設定區 (雲端展示去敏感版) ---
MY_TOKEN = "YOUR_FINMIND_TOKEN_PLACEHOLDER"
SCAN_LIST = ["2330", "2317", "2454", "1101", "2603", "2303", "2881", "2882"] 

TG_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_PLACEHOLDER"
TG_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID_PLACEHOLDER"
CSV_FILE = "financial_scan_results.csv"

def get_stock_name_map(fetcher):
    try:
        df_info = fetcher.api.taiwan_stock_info()
        return dict(zip(df_info['stock_id'], df_info['stock_name']))
    except:
        return {}

def run_financial_scan():
    print(f"\n🚀 財報獵人啟動中...")
    
    fetcher = FinDataFetcher(MY_TOKEN)
    notifier = TelegramNotifier(TG_TOKEN, TG_CHAT_ID)
    name_map = get_stock_name_map(fetcher)
    current_month = datetime.now().strftime("%Y-%m") 
    
    if os.path.exists(CSV_FILE):
        try:
            existing_df = pd.read_csv(CSV_FILE, dtype={'代號': str})
            if "營營收YoY" in existing_df.columns:
                existing_df = existing_df.rename(columns={"營營收YoY": "營收YoY"})
            
            history_results = existing_df.set_index('代號').to_dict('index')
            print(f"📂 偵測到現有進度，載入 {len(history_results)} 檔紀錄。")
        except Exception:
            history_results = {}
            print("⚠️ 現有 CSV 格式損壞，將重新開始掃描。")
    else:
        history_results = {}
        print("🆕 無現有紀錄，將開始全新掃描。")

    final_results_list = []
    new_matches = [] 
    
    print("\n" + "="*20 + " 今日財報掃描清單 " + "="*20)
    header = f"{'代號':<5} | {'單季EPS':<8} | {'EPS 4Q':<7} | {'毛利%':<7} | {'現金流(億)':<10} | {'殖利率%':<7} | {'營收YoY':<7} | {'判定'}"
    print(header)
    print("-" * len(header))

    for i, sid in enumerate(SCAN_LIST):
        # 1. 增量檢查
        if sid in history_results:
            h = history_results[sid]
            last_period = str(h.get('掃描月份', ""))
            if last_period == current_month:
                yoy_val = h.get('營收YoY', h.get('營營收YoY', '0.0%'))
                row_str = (f"{sid:<5} | {h['單季EPS']:>8.2f} | {h['EPS_4Q']:>7.2f} | "
                           f"{h['毛利率']:>7} | {h['營運現金流(億)']:>10.1f} | "
                           f"{h['殖利率']:>7} | {yoy_val:>7} | {h['符合類型']} (已跳過)")
                print(row_str)
                final_results_list.append({**h, "代號": sid, "營收YoY": yoy_val})
                continue
        
        # 2. 執行新掃描
        try:
            rev_df, fin_df, current_price = fetcher.process_single_stock(sid)
            if rev_df is None or fin_df is None or fin_df.empty:
                continue
                
            latest = fin_df.iloc[-1]
            latest_rev_yoy = rev_df['revenue_comparison_month'].iloc[-1] if 'revenue_comparison_month' in rev_df.columns else 0
            real_yield = (latest['dividend_last_year'] / current_price * 100) if current_price > 0 else 0
            ocf_billion = latest['operating_cash_flow'] / 100000000
            
            matches = []
            if StockStrategy.check_growth(rev_df, fin_df, current_price).get('match'): matches.append("成長")
            if StockStrategy.check_recession(rev_df, fin_df).get('match'): matches.append("衰退")
            if StockStrategy.check_turnaround(rev_df, fin_df, current_price).get('match'): matches.append("轉機")
            if StockStrategy.check_value(fin_df, current_price).get('match'): matches.append("價值")
            if StockStrategy.check_buffett(fin_df, current_price).get('match'): matches.append("巴菲特")

            res_str = " | ".join(matches) if matches else "不符合"
            s_name = name_map.get(sid, "")

            row_str = (f"{sid:<5} | {latest['eps']:>8.2f} | {latest['eps_4q_sum']:>7.2f} | "
                       f"{latest['gross_profit_margin']:>6.1f}% | {ocf_billion:>10.1f} | "
                       f"{real_yield:>7.1f}% | {latest_rev_yoy:>7.1f}% | {res_str}")
            print(row_str)

            stock_data = {
                "代號": sid, "股名": s_name, "符合類型": res_str, 
                "單季EPS": round(latest['eps'], 2), "EPS_4Q": round(latest['eps_4q_sum'], 2), 
                "毛利率": f"{latest['gross_profit_margin']:.1f}%",
                "營運現金流(億)": round(ocf_billion, 2), "殖利率": f"{real_yield:.1f}%", 
                "營收YoY": f"{latest_rev_yoy:.1f}%",
                "掃描月份": current_month 
            }
            final_results_list.append(stock_data)
            if res_str != "不符合": new_matches.append(stock_data)
            pd.DataFrame(final_results_list).to_csv(CSV_FILE, index=False, encoding='utf-8-sig')

        except Exception:
            continue

    print("-" * len(header))
    print(f"\n✅ 掃描任務完成！")
    
    # --- 觸發自動同步 (移至所有迴圈完成後，只執行一次) ---
    auto_sync_to_reg_hunter()
    
    # --- 推播訊息組裝 (已補全所有數據) ---
    if new_matches:
        msg = f"<b>🔍 財報獵人：發現新標的 ({current_month})</b>\n========================\n"
        for target in new_matches:
            name_info = f" - {target['股名']}" if target['股名'] else ""
            msg += f"<b>📈 {target['代號']}{name_info}</b>\n"
            msg += f"策略判定：<code>{target['符合類型']}</code>\n"
            msg += f"單季EPS：{target['單季EPS']} | EPS 4Q：{target['EPS_4Q']}\n"
            msg += f"營收YoY：{target['營收YoY']} | 毛利率：{target['毛利率']}\n"
            msg += f"殖利率：{target['殖利率']} | 現金流：{target['營運現金流(億)']}億\n"
            msg += "------------------------\n"
        notifier.send_to_all(msg)
        print(f"📢 已推播 {len(new_matches)} 檔詳細數據至 Telegram。")

if __name__ == "__main__":
    run_financial_scan()