import streamlit as st
import pandas as pd
import os
import sys
from datetime import datetime, timedelta
from data_fetcher import FinDataFetcher
from strategies import StockStrategy
from notifier import TelegramNotifier
from sync_utils import auto_sync_to_reg_hunter

# --- 關閉 FinMind 的干擾訊息 ---
from loguru import logger
logger.remove() 
logger.add(sys.stderr, level="WARNING")

# --- 頁面基本設定 ---
st.set_page_config(page_title="財報獵人深度儀表板", layout="wide")
st.title("🏹 台股財報獵人：全市場財報掃描系統")
st.markdown('<p style="color: #808495; font-size: 0.85rem; padding-left: 80px; margin-top: -15px;">ℹ️ 此為展示版，數據會持續自動更新但手動掃描等按鈕不會作動</p>', unsafe_allow_html=True)

# --- 系統核心設定 ---
MY_FINMIND_TOKEN = "DEMO"
TG_TOKEN = None
TG_CHAT_ID = None
CSV_FILE = "financial_scan_results.csv"

# 初始化通知器
notifier = TelegramNotifier(TG_TOKEN, TG_CHAT_ID)

# --- 側邊欄控制區 ---
with st.sidebar:
    st.header("🔔 訂閱推播")
    new_tg_token = st.text_input("Telegram Bot Token")
    new_chat_id = st.text_input("Telegram Chat ID")
    if st.button("儲存訂閱資訊"):
        if new_tg_token and new_chat_id:
            notifier.save_subscriber(new_tg_token, new_chat_id)
            st.success("訂閱成功！")
    
    # 修改後的推播說明文字
    st.caption("請輸入 Telegram Bot資訊。系統將於營收與財報發布日，即時將符合篩選條件之標的推送至您的行動裝置。")

    st.divider()
    auto_update_revenue = st.checkbox("啟動營收自動更新", value=False)
    auto_update_quarter = st.checkbox("啟動季報自動更新", value=False)
    st.caption("啟用後每 65 分鐘會自動執行一次掃描。")
    if 'last_update_time' in st.session_state and st.session_state.last_update_time:
        st.caption(f"上次掃描時間: {st.session_state.last_update_time}")

# --- 主視覺：數據摘要區 ---
if os.path.exists(CSV_FILE):
    try:
        df_all = pd.read_csv(CSV_FILE, dtype={'代號': str})
        
        # --- 雲端版專屬：自動偵測本機同步過來的 CSV 更新並推播給其它註冊的雲端訂閱者 ---
        # 雲端版排除開發者 Token 避免重複推播，預設 notifier 的 default_token/chat_id 為 None
        try:
            if '最後掃描時間' in df_all.columns and not df_all.empty:
                latest_scan_time_str = str(df_all['最後掃描時間'].max())
                
                state_file = "last_notified_time.txt"
                last_notified_str = ""
                if os.path.exists(state_file):
                    with open(state_file, "r", encoding="utf-8") as sf:
                        last_notified_str = sf.read().strip()
                
                if latest_scan_time_str != last_notified_str:
                    # 立即寫入狀態檔，防範並發載入導致重複發送
                    with open(state_file, "w", encoding="utf-8") as sf:
                        sf.write(latest_scan_time_str)
                    
                    # 找出在這一批最新掃描時間中，符合策略的股票
                    new_batch_df = df_all[df_all['最後掃描時間'] == latest_scan_time_str]
                    new_matches = []
                    for _, row in new_batch_df.iterrows():
                        res_str = str(row.get('符合類型', '不符合'))
                        if res_str and res_str != "不符合":
                            new_matches.append(row)
                    
                    if new_matches:
                        subscribers = notifier.get_all_subscribers()
                        valid_subs = [s for s in subscribers if s.get('token') and s.get('chat_id')]
                        if valid_subs:
                            for row in new_matches:
                                msg = f"🎯 <b>財報獵人發現標的 (雲端版推送)！</b>\n" \
                                      f"股票：{row['代號']} {row.get('股名', '')}\n" \
                                      f"符合類型：{row.get('符合類型', '')}\n" \
                                      f"最新毛利：{row.get('毛利率', '')}\n" \
                                      f"近四季ROE：{row.get('近四季ROE', '')}\n" \
                                      f"本益比：{row.get('本益比', '')}\n" \
                                      f"掃描時間：{latest_scan_time_str}"
                                notifier.send_to_all(msg)
        except Exception as e:
            pass
        # 顯示用：每支股票只取最新掃描月份的資料（包含最新營收與財報）
        if '掃描月份' in df_all.columns and not df_all.empty:
            df = df_all.sort_values('掃描月份').groupby('代號', as_index=False).last()
        else:
            df = df_all.drop_duplicates(subset=['代號'], keep='last')
        
        if '符合類型' in df.columns:
            count_total = len(df)
            count_growth = len(df[df['符合類型'].str.contains("成長", na=False)])
            count_recession = len(df[df['符合類型'].str.contains("衰退", na=False)])
            count_turnaround = len(df[df['符合類型'].str.contains("轉機", na=False)])
            count_value = len(df[df['符合類型'].str.contains("價值", na=False)])
            count_buffett = len(df[df['符合類型'].str.contains("巴菲特", na=False)])
        else:
            count_total = count_growth = count_recession = count_turnaround = count_value = count_buffett = 0
    except Exception:
        df_all = pd.DataFrame()
        df = pd.DataFrame()
        count_total = count_growth = count_recession = count_turnaround = count_value = count_buffett = 0
else:
    df_all = pd.DataFrame()
    df = pd.DataFrame()
    count_total = count_growth = count_recession = count_turnaround = count_value = count_buffett = 0

if count_total > 0 or not df.empty:
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("已掃瞄總數", count_total)
    m2.metric("成長股", count_growth)
    m3.metric("衰退股", count_recession)
    m4.metric("轉機股", count_turnaround)
    m5.metric("一般價值股", count_value)
    m6.metric("巴菲特價值股", count_buffett)
else:
    st.info("尚無掃描紀錄，請點擊下方按鈕開始掃描。")

# --- 啟動按鈕與進度顯示 ---
should_scan = False
scan_mode = None

if 'last_update_time' not in st.session_state:
    st.session_state.last_update_time = None

if auto_update_revenue or auto_update_quarter:
    if st.session_state.last_update_time is None:
        should_scan = True
        scan_mode = 'revenue' if auto_update_revenue else 'quarter'
    else:
        fmt = "%Y-%m-%d %H:%M:%S"
        try:
            last_time = datetime.strptime(st.session_state.last_update_time, fmt)
            if (datetime.now() - last_time).total_seconds() >= 65 * 60:
                should_scan = True
                scan_mode = 'revenue' if auto_update_revenue else 'quarter'
        except Exception:
            should_scan = True
            scan_mode = 'revenue' if auto_update_revenue else 'quarter'

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    if st.button("🚀 啟動營收掃描", use_container_width=True):
        should_scan = True
        scan_mode = 'revenue'
with col_btn2:
    if st.button("🚀 啟動季報掃描", use_container_width=True):
        should_scan = True
        scan_mode = 'quarter'
if should_scan:
    st.info("⚠️ 此為雲端展示版，數據已在本機全自動排程掃描與同步，手動掃描與自動更新核取方塊僅供功能展示，暫無功能。")
    should_scan = False

if should_scan:
    st.session_state.last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fetcher = FinDataFetcher(MY_FINMIND_TOKEN)
    
    try:
        stock_info = fetcher.api.taiwan_stock_info()
        all_stocks = [sid for sid in stock_info['stock_id'].tolist() if len(sid) == 4]
        name_map = dict(zip(stock_info['stock_id'], stock_info['stock_name']))
        type_map = dict(zip(stock_info['stock_id'], stock_info['type']))
        market_map = {k: "上市" if v == "twse" else "上櫃" if v == "tpex" else "興櫃" if v == "emerging" else v for k, v in type_map.items()}
    except Exception as e:
        st.error(f"無法取得全市場股票清單: {e}")
        if auto_update:
            import time
            time.sleep(65 * 60)
            st.rerun()
        st.stop()
    
    # --- 智慧過濾邏輯設定 ---
    now = datetime.now()
    # 目標營收月份：通常本月 10 號前要抓上個月，10 號後也是抓上個月（直到最新公佈）
    # 這裡採簡單邏輯：目標為上個月的營收年月
    first_day_of_this_month = now.replace(day=1)
    target_rev_date = (first_day_of_this_month - timedelta(days=1)).strftime("%Y-%m")
    
    # 準備現有資料以供後續合併
    existing_df = df_all.copy() if not df_all.empty else pd.DataFrame()
    
    # 建立歷史索引以利快速比對
    history_dict = {}
    if not df_all.empty:
        # 只取每支股票最後一筆紀錄作為頻率判斷基準
        latest_records = df_all.sort_values('最後掃描時間').groupby('代號').last()
        history_dict = latest_records.to_dict('index')

    stocks_to_scan = []
    for sid in all_stocks:
        if sid in history_dict:
            h = history_dict[sid]
            h_rev_month = str(h.get('營收年月', ""))[:7] # YYYY-MM
            h_last_time_str = str(h.get('最後掃描時間', ""))
            h_daily_count = h.get('當日掃描次數', 0)
            
            # 1. 根據掃描模式決定是否跳過
            if scan_mode == 'revenue':
                if h_rev_month >= target_rev_date:
                    continue
            else:
                # 季報掃描模式下，先暫不跳過（確保全面更新財報）
                pass
                
            # 2. 頻率限制判定
            try:
                h_last_time = datetime.strptime(h_last_time_str, "%Y-%m-%d %H:%M:%S")
                is_same_day = h_last_time.date() == now.date()
                
                if is_same_day:
                    # 同一天內：檢查次數與間隔
                    time_diff = (now - h_last_time).total_seconds() / 3600
                    if h_daily_count >= 2: continue # 一天最多2次
                    if time_diff < 10: continue      # 間隔至少10小時
                else:
                    # 不同天：計數器會重置，允許掃描
                    pass
            except:
                pass # 格式錯誤或無紀錄則允許掃描
        
        stocks_to_scan.append(sid)
    
    if not stocks_to_scan:
        st.success("所有標的營收已達標或尚未達到重試間隔。")
        if auto_update_revenue or auto_update_quarter:
            import time
            time.sleep(65 * 60)
            st.rerun()
        st.stop()

    # 用於紀錄是否發生「歷史財報不足」的狀況
    insufficient_history_flag = False

    st.write(f"📊 待掃描數量: {len(stocks_to_scan)} 檔 (批量模式)")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    new_results_list = []  # 本次掃描新增的結果
    chunk_size = 30 
    
    for i in range(0, len(stocks_to_scan), chunk_size):
        chunk = stocks_to_scan[i:i + chunk_size]
        percent = (i + len(chunk)) / len(stocks_to_scan)
        progress_bar.progress(percent)
        status_text.text(f"🔍 正在批量處理：{chunk[0]} ~ {chunk[-1]}")
        
        if scan_mode == 'revenue':
            batch_results = fetcher.fetch_revenue_only_in_batches(chunk, chunk_size=chunk_size)
        else:
            batch_results = fetcher.fetch_data_in_batches(chunk, chunk_size=chunk_size)
        
        if not batch_results:
            continue

        for sid, (rev_df, fin_df, current_price) in batch_results.items():
            try:
                skip_strategy = False
                res_str = "不符合"
                fin_quarter = ""
                
                if scan_mode == 'revenue':
                    if df_all.empty or '財報季度' not in df_all.columns:
                        continue # 營收掃描需要依賴舊財報，若無紀錄直接跳過
                    
                    hist_df = df_all[df_all['代號'] == sid].drop_duplicates('財報季度', keep='last').sort_values('財報季度')
                    if len(hist_df) < 1:
                        continue # 無任何舊紀錄，無法重建

                    if len(hist_df) < 3:
                        skip_strategy = True
                        insufficient_history_flag = True
                        res_str = str(hist_df['符合類型'].iloc[-1]) # 繼承舊狀態
                    
                    fin_quarter = str(hist_df['財報季度'].iloc[-1])
                    
                    # 重建 mock fin_df 給策略模組與顯示欄位使用
                    mock_fin_list = []
                    for _, row in hist_df.tail(3).iterrows():
                        def parse_pct(val):
                            if isinstance(val, str) and '%' in val: return float(val.replace('%', ''))
                            return float(val) if pd.notna(val) else 0.0
                            
                        mock_row = {
                            'eps_4q_sum': float(row.get('近四季EPS', 0)),
                            'equity': float(row.get('淨值(億)', 0)) * 100000000,
                            'shares': float(row.get('股本(億)', 0)) * 100000000 / 10,
                            'total_assets': 100, # mock
                            'total_liabilities': parse_pct(row.get('負債比', '0%')), # 暫以負債比代入，確保下方計算 debt_ratio 正確
                            'debt_ratio': parse_pct(row.get('負債比', '0%')),
                            'free_cash_flow': float(row.get('自由現金流(億)', 0)) * 100000000,
                            'dividend_last_year': (float(row.get('殖利率', '0%').replace('%', '')) / 100) * current_price if current_price > 0 else 0,
                            'roe_4q': parse_pct(row.get('近四季ROE', '0%')),
                            'roe_1q': parse_pct(row.get('季ROE', '0%')),
                            'eps_yoy_1q': parse_pct(row.get('季EPS YoY', '0%')),
                            'eps': float(row.get('季EPS', 0)),
                            'gross_profit_margin': parse_pct(row.get('毛利率', '0%')),
                            'operating_cash_flow': float(row.get('營運現金流(億)', 0)) * 100000000,
                            'nav_per_share': float(row.get('每股淨值', 0)),
                            'book_value_per_share': float(row.get('每股淨值', 0))
                        }
                        mock_fin_list.append(mock_row)
                    fin_df = pd.DataFrame(mock_fin_list)
                    
                if rev_df is not None and not rev_df.empty and fin_df is not None and not fin_df.empty:
                    latest = fin_df.iloc[-1]
                    latest_rev_yoy = rev_df['revenue_comparison_month'].iloc[-1] if 'revenue_comparison_month' in rev_df.columns else 0
                    eps_4q = latest.get('eps_4q_sum', 0)
                    pe_ratio = current_price / eps_4q if eps_4q > 0 else 0
                    shares = latest.get('shares', 0)
                    equity = latest.get('equity', 0)
                    pb_ratio = current_price / (equity / shares) if (shares > 0 and equity > 0) else 0
                    assets = latest.get('total_assets', 0)
                    liabilities = latest.get('total_liabilities', 0)
                    debt_ratio = latest.get('debt_ratio', 0) if scan_mode == 'revenue' else (liabilities / assets * 100 if assets > 0 else 0)
                    fcf_billion = latest.get('free_cash_flow', 0) / 100000000
                    real_yield = (latest.get('dividend_last_year', 0) / current_price * 100) if current_price > 0 else 0
                    
                    if scan_mode != 'revenue':
                        # --- 推算財報季度（從財報日期的月份判斷）---
                        try:
                            fin_date_str = str(latest.get('date', ''))
                            fin_month = int(fin_date_str[5:7])
                            fin_year = int(fin_date_str[:4])
                            fin_q = (fin_month - 1) // 3 + 1
                            fin_quarter = f"{fin_year}Q{fin_q}"
                        except Exception:
                            fin_quarter = ""
                    
                    if not skip_strategy:
                        matches = []
                        if StockStrategy.check_growth(rev_df, fin_df, current_price).get('match'): matches.append("成長")
                        if StockStrategy.check_recession(rev_df, fin_df).get('match'): matches.append("衰退")
                        if StockStrategy.check_turnaround(rev_df, fin_df, current_price).get('match'): matches.append("轉機")
                        if StockStrategy.check_value(fin_df, current_price).get('match'): matches.append("價值")
                        if StockStrategy.check_buffett(fin_df, current_price).get('match'): matches.append("巴菲特")
                        res_str = " | ".join(matches) if matches else "不符合"
                    # 系統內的roe_4q已經在擷取時修正，這裡是正確值
                    roe_4q_corrected = latest.get('roe_4q', 0)  # 近四季ROE
                    roe_1q = latest.get('roe_1q', 0)  # 單季ROE
                    eps_yoy_1q = latest.get('eps_yoy_1q', 0)  # 單季EPS YoY
                    # 營收年月：從 rev_df 取得最後一筆日期
                    rev_date = str(rev_df['date'].iloc[-1])[:7] if not rev_df.empty else ""
                    
                    # 更新當日掃描次數
                    new_count = 1
                    if sid in history_dict:
                        last_t_str = str(history_dict[sid].get('最後掃描時間', ""))
                        try:
                            last_t = datetime.strptime(last_t_str, "%Y-%m-%d %H:%M:%S")
                            if last_t.date() == now.date():
                                new_count = history_dict[sid].get('當日掃描次數', 0) + 1
                        except: pass

                    stock_data = {
                        "代號": sid,
                        "股名": name_map.get(sid, ""), 
                        "市場類型": market_map.get(sid, ""),
                        "符合類型": res_str,
                        "營收YoY": f"{latest_rev_yoy:.1f}%",
                        "季EPS": round(latest.get('eps', 0), 2), 
                        "季EPS YoY": f"{eps_yoy_1q:.1f}%",
                        "近四季EPS": round(eps_4q, 2), 
                        "毛利率": f"{latest.get('gross_profit_margin', 0):.1f}%",
                        "季ROE": f"{roe_1q:.1f}%",
                        "近四季ROE": f"{roe_4q_corrected:.1f}%",
                        "本益比": round(pe_ratio, 2),
                        "股價淨值比": round(pb_ratio, 2),
                        "殖利率": f"{real_yield:.1f}%", 
                        "負債比": f"{debt_ratio:.1f}%",
                        "營運現金流(億)": round(latest.get('operating_cash_flow', 0) / 100000000, 2), 
                        "自由現金流(億)": round(fcf_billion, 2),
                        "營收年月": rev_date,
                        "財報季度": fin_quarter,
                        "掃描月份": now.strftime("%Y-%m"),
                        "最後掃描時間": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "當日掃描次數": new_count,
                        "每股淨值": round(latest.get('nav_per_share', latest.get('book_value_per_share', 0)), 2),
                        "淨值(億)": round(equity / 100000000, 2),
                        "股本(億)": round((shares * 10) / 100000000, 2)
                    }
                    new_results_list.append(stock_data)
                    
                    # --- 自動發送 Telegram 推播 ---
                    if matches:
                        msg = f"🎯 <b>財報獵人發現標的！</b>\n" \
                              f"股票：{sid} {stock_data['股名']}\n" \
                              f"財報季度：{fin_quarter}\n" \
                              f"符合類型：{res_str}\n" \
                              f"最新毛利：{stock_data['毛利率']}\n" \
                              f"近四季ROE：{stock_data['近四季ROE']}\n" \
                              f"本益比：{stock_data['本益比']}\n" \
                              f"價格：{current_price}"
                        notifier.send_to_all(msg)
            except Exception as e:
                print(f"⚠️ 處理股票 {sid} 時發生錯誤: {e}")
                continue
        
        if new_results_list:
            new_df = pd.DataFrame(new_results_list)
            cols_to_save = ["代號", "股名", "市場類型", "符合類型", "營收YoY", "季EPS", "季EPS YoY", "近四季EPS", "毛利率", "季ROE", "近四季ROE", "本益比", "股價淨值比", "殖利率", "負債比", "營運現金流(億)", "自由現金流(億)", "每股淨值", "淨值(億)", "股本(億)", "營收年月", "財報季度", "掃描月份", "最後掃描時間", "當日掃描次數"]
            new_df = new_df[[c for c in cols_to_save if c in new_df.columns]]
            # 合併歷史各季資料與本次新掃描結果，以(代號,財報季度)去重
            if not existing_df.empty:
                combined = pd.concat([existing_df, new_df], ignore_index=True)
                if '掃描月份' in combined.columns:
                    combined = combined.drop_duplicates(subset=['代號', '掃描月份'], keep='last')
                else:
                    combined = combined.drop_duplicates(subset=['代號'], keep='last')
            else:
                combined = new_df
            if '掃描月份' in combined.columns:
                combined = combined.sort_values(['代號', '掃描月份'])
            combined.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')
            existing_df = combined  # 更新，供下一批次使用

    st.success(f"掃描完成！")
    if insufficient_history_flag:
        st.session_state.show_history_warning = True
        
    # --- 觸發自動同步 (移至所有迴圈完成後，只執行一次) ---
    auto_sync_to_reg_hunter()
    
    st.rerun()

if st.session_state.get('show_history_warning', False):
    st.warning("⚠️ 歷史財報不足三季，無法判定，符合類型不做變動。")
    st.session_state.show_history_warning = False

# --- 數據表格 ---
if not df.empty and '符合類型' in df.columns:
    st.divider()
    st.subheader("📊 財報掃描結果清單")
    
    display_cols = ["代號", "股名", "符合類型", "營收YoY", "季EPS", "季EPS YoY", "近四季EPS", "毛利率", "季ROE", "近四季ROE", "本益比", "股價淨值比", "殖利率", "負債比", "營運現金流(億)", "自由現金流(億)", "財報季度", "掃描月份"]
    existing_cols = [c for c in display_cols if c in df.columns]
    display_df = df[existing_cols].drop_duplicates(subset=['代號'], keep='last')

    # 自動排序，符合策略的股票排在最上方
    display_df['is_match'] = display_df['符合類型'].apply(lambda x: 0 if x == "不符合" else 1)
    display_df = display_df.sort_values(by='is_match', ascending=False).drop(columns=['is_match'])
    
    format_dict = {
        '季EPS': '{:.2f}', '近四季EPS': '{:.2f}', 
        '本益比': '{:.2f}', '股價淨值比': '{:.2f}',
        '營運現金流(億)': '{:.2f}', '自由現金流(億)': '{:.2f}'
    }

    st.dataframe(display_df.style.format(format_dict, na_rep='-'), use_container_width=True, height=600)

# --- 策略說明區 ---
st.divider()
st.subheader("📝 策略篩選邏輯說明")
col_info1, col_info2 = st.columns(2)

with col_info1:
    with st.expander("📈 成長股 (Growth Stock)"):
        st.markdown("""
        **篩選核心：營收動能與獲利品質兼具**
        * **營收動能**：連續 2 個月營收年增率 (YoY)>20%且近月較前月高。
        * **獲利品質**：股東權益報酬率 單季(ROE) ≥ 5% 近四季(ROE) ≥ 15%。
        * **獲利品質**：每股盈餘年增率 單季(EPS YoY)>20%。
        * **本業強度**：毛利率 ≥ 20% 且 營運現金流必須為正數 (> 0)。
        * **強勢加註**：若 PEG (本益成長比) < 0.75，則判定為「強勢成長」。
        """)
    with st.expander("📉 衰退股 (Recession Stock)"):
        st.markdown("""
        **篩選核心：營運全面轉弱的警訊**
        * **營收低落**：連續 3 個月營收年增率(YoY)<0%。
        * **獲利倒退**：連續二季EPS年增率(YoY)<0%且負值擴大。
        * **競爭力下滑**：毛利率連續二季下降。
        * **資金壓力**：最新一季自由現金流為負數。
        """)
    with st.expander("🔄 轉機股 (Turnaround Stock)"):
        st.markdown("""
        **篩選核心：從虧損轉向獲利的新生力量**
        * **虧轉盈**：前一季 EPS < 0，最新一季 EPS > 0。
        * **獲利改善**：最新一季毛利率高於前一季。
        * **營收回溫**：營收YoY連續二個月>0。
        * **獲利品質**：營運現金流>0。
        * **安全邊際**：股價淨值比 (PB)低於2倍。
        """)
with col_info2:
    with st.expander("💰 一般價值股 (Value Stock)"):
        st.markdown("""
        **篩選核心：股價被低估的安全邊際**
        * **本益比 (PE)**：處於合理區間 (0 < PE < 12)。
        * **股價淨值比 (PB)**：低於 1.2 倍。
        * **高殖利率**：最新一年配息殖利率 > 5%。
        * **獲利穩定**：股東權益報酬率 近四季(ROE) ≥ 8%。
        * **負債比率**：低於 50%。
        * **資金充裕**：自由現金流 (Free Cash Flow) > 0。
        """)
    with st.expander("💎 巴菲特價值股 (Buffett Style)"):
        st.markdown("""
        **篩選核心：優質護城河與卓越長線績效**
        * **高報酬率**：連續2年股東權益報酬率 (ROE) > 20%。
        * **極低負債**：負債比率 < 35%。
        * **優勢產品**：最新毛利率 > 30%。
        * **安全邊際**：本益比 (PE)低於15倍。
        * **真金白銀**：自由現金流 (Free Cash Flow) > 0。
        """)

# --- 頁面底部版權宣告 ---
st.divider()
foot_c1, foot_c2, foot_c3 = st.columns([2, 1, 2])
with foot_c2:
    st.caption("© 2026 Built by 趙志軒")

if (auto_update_revenue or auto_update_quarter) and not should_scan:
    import time
    time.sleep(65 * 60)
    st.rerun()