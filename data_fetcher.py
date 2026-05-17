import pandas as pd
import numpy as np
import logging
from FinMind.data import DataLoader
from datetime import datetime, timedelta

logging.getLogger('FinMind').setLevel(logging.WARNING)

class FinDataFetcher:
    def __init__(self, token):
        self.api = DataLoader()
        self.api.login_by_token(token)
        self.start_date = (datetime.now() - timedelta(days=1100)).strftime('%Y-%m-%d')
        self.price_start_date = (datetime.now() - timedelta(days=15)).strftime('%Y-%m-%d')

    def process_single_stock(self, stock_id):
        """處理單支股票的所有數據"""
        try:
            raw_rev = self.api.taiwan_stock_month_revenue(stock_id=[stock_id], start_date=self.start_date)
            raw_is = self.api.taiwan_stock_financial_statement(stock_id=[stock_id], start_date=self.start_date)
            raw_bs = self.api.taiwan_stock_balance_sheet(stock_id=[stock_id], start_date=self.start_date)
            raw_cf = self.api.taiwan_stock_cash_flows_statement(stock_id=[stock_id], start_date=self.start_date)
            raw_price = self.api.taiwan_stock_daily(stock_id=[stock_id], start_date=self.price_start_date)
            raw_div = self.api.taiwan_stock_dividend(stock_id=[stock_id], start_date=self.start_date)
            
            return self.calculate_indicators(stock_id, raw_rev, raw_is, raw_bs, raw_cf, raw_price, raw_div)
        except Exception as e:
            print(f"❌ 處理 {stock_id} 失敗: {e}")
            return None, None, 0

    def fetch_data_in_batches(self, stock_id_list, chunk_size=30):
        all_results = {}
        for i in range(0, len(stock_id_list), chunk_size):
            chunk = stock_id_list[i:i + chunk_size]
            try:
                raw_rev = self.api.taiwan_stock_month_revenue(stock_id=chunk, start_date=self.start_date)
                raw_is = self.api.taiwan_stock_financial_statement(stock_id=chunk, start_date=self.start_date)
                raw_bs = self.api.taiwan_stock_balance_sheet(stock_id=chunk, start_date=self.start_date)
                raw_cf = self.api.taiwan_stock_cash_flows_statement(stock_id=chunk, start_date=self.start_date)
                raw_price = self.api.taiwan_stock_daily(stock_id=chunk, start_date=self.price_start_date)
                raw_div = self.api.taiwan_stock_dividend(stock_id=chunk, start_date=self.start_date)

                for sid in chunk:
                    s_rev = raw_rev[raw_rev['stock_id'] == sid] if not raw_rev.empty else pd.DataFrame()
                    s_is = raw_is[raw_is['stock_id'] == sid] if not raw_is.empty else pd.DataFrame()
                    s_bs = raw_bs[raw_bs['stock_id'] == sid] if not raw_bs.empty else pd.DataFrame()
                    s_cf = raw_cf[raw_cf['stock_id'] == sid] if not raw_cf.empty else pd.DataFrame()
                    s_price = raw_price[raw_price['stock_id'] == sid] if not raw_price.empty else pd.DataFrame()
                    s_div = raw_div[raw_div['stock_id'] == sid] if not raw_div.empty else pd.DataFrame()

                    rev_df, fin_df, price = self.calculate_indicators(sid, s_rev, s_is, s_bs, s_cf, s_price, s_div)
                    all_results[sid] = (rev_df, fin_df, price)
            except Exception as e:
                print(f"❌ 批量處理失敗: {e}")
                continue
        return all_results

    def fetch_revenue_only_in_batches(self, stock_id_list, chunk_size=30):
        all_results = {}
        for i in range(0, len(stock_id_list), chunk_size):
            chunk = stock_id_list[i:i + chunk_size]
            try:
                raw_rev = self.api.taiwan_stock_month_revenue(stock_id=chunk, start_date=self.start_date)
                raw_price = self.api.taiwan_stock_daily(stock_id=chunk, start_date=self.price_start_date)

                for sid in chunk:
                    s_rev = raw_rev[raw_rev['stock_id'] == sid] if not raw_rev.empty else pd.DataFrame()
                    s_price = raw_price[raw_price['stock_id'] == sid] if not raw_price.empty else pd.DataFrame()

                    current_price = s_price['close'].iloc[-1] if not s_price.empty else 0
                    
                    # 依照原有邏輯整理 rev DataFrame，但不計算財報
                    if not s_rev.empty:
                        s_rev = s_rev.sort_values('date')
                    
                    all_results[sid] = (s_rev, None, current_price)
            except Exception as e:
                print(f"❌ 批量營收處理失敗: {e}")
                continue
        return all_results

    def calculate_indicators(self, sid, rev, fin_is, fin_bs, fin_cf, price_df, div_df):
        try:
            if fin_is.empty or rev.empty:
                return None, None, 0

            yoy_col = next((c for c in rev.columns if 'revenue_comparison_month' in c or 'revenue_year_growth' in c), None)
            rev = rev.copy()
            rev['revenue_comparison_month'] = rev[yoy_col] if yoy_col else rev['revenue'].pct_change(12) * 100

            all_fin = pd.concat([fin_is, fin_bs, fin_cf], ignore_index=True)
            fin_wide = all_fin.pivot_table(index='date', columns='origin_name', values='value', aggfunc='mean').reset_index()
            
            df = pd.DataFrame(index=fin_wide.index)
            df['date'] = fin_wide['date']
            
            def safe_get(keywords):
                cols = [c for c in fin_wide.columns if any(k == str(c) or k in str(c) for k in keywords)]
                return fin_wide[cols[0]] if cols else pd.Series([0.0] * len(fin_wide))

            # --- 基本資料提取 ---
            net_income = safe_get(['本期淨利', '本期純益', '歸屬於母公司業主之權益', '合併淨損益'])
            f_equity = safe_get(['權益總額', '權益總計', '股東權益總額']) * 2
            f_asset = safe_get(['資產總額', '資產總計'])
            f_debt = safe_get(['負債總額', '負債總計'])
            f_shares_val = safe_get(['股本', '普通股股本', '股本合計']) * 2

            # --- 核心計算優化 ---
            df['eps'] = safe_get(['基本每股盈餘', '每股盈餘', 'EPS'])
            df['eps_4q_sum'] = df['eps'].rolling(4).sum()
            
            # 計算單季EPS YoY (年增率)
            # 單季EPS YoY = (當季EPS - 去年同季EPS) / 去年同季EPS * 100
            # 由於資料是按季度排列，去年同季 = 4季前的資料
            eps_yoy_4q_prior = df['eps'].shift(4)
            df['eps_yoy_1q'] = ((df['eps'] - eps_yoy_4q_prior) / eps_yoy_4q_prior.abs() * 100).fillna(0)
            
            # ======== ROE 計算說明 ========
            # 因為已於取值時將 f_equity 乘以 2 修正了減半問題，
            # 此處計算出的 roe_4q 已經是正確值，不需要再除以 2。
            # ========================================
            
            # 計算近四季ROE (4Q_ROE)
            # 使用 (近四季淨利和 / 平均權益) 更能反映全年營運效率
            # 平均權益 = (期末權益 + 期初權益) / 2，其中期初權益為四季前的期末權益
            df['equity_4q_prior'] = f_equity.shift(4)
            # 對於缺失的期初權益（前4季），用期末權益替代
            df['equity_4q_prior'] = df['equity_4q_prior'].fillna(f_equity)
            df['equity_avg'] = (f_equity + df['equity_4q_prior']) / 2
            df['roe_4q'] = (net_income.rolling(4).sum() / df['equity_avg']).fillna(0) * 100
            
            # 計算單季ROE (基於最新一季的EPS和期末權益)
            # 單季ROE = (單季淨利 / 期末權益) * 100 = (EPS * 股數 / 權益) * 100
            # 為了簡化計算，我們使用: 單季ROE ≈ (單季EPS / (權益/股數)) * 100
            # 但由於資料限制，直接使用EPS計算: 單季ROE = EPS * 100 / (期末權益 / 股數)
            # 簡化版：單季ROE = (EPS / (每股淨值)) * 100，其中每股淨值 = 權益 / 股數
            df['book_value_per_share'] = f_equity / (f_shares_val / 10)  # 每股淨值
            df['nav_per_share'] = safe_get(['每股參考淨值', '每股淨值'])
            if df['nav_per_share'].sum() == 0:
                df['nav_per_share'] = df['book_value_per_share']
            df['roe_1q'] = (df['eps'] / df['book_value_per_share'] * 100).fillna(0)
            
            # PB 修正：(權益 * 10 / 股本) = 每股淨值，單位皆為千元，相互抵消
            # 為符合 app.py 邏輯，我們回傳正確單位的 shares 和 equity
            df['equity'] = f_equity
            df['shares'] = f_shares_val / 10  # 股本除以面額10 = 總股數 (單位：張)
            
            df['total_assets'] = f_asset
            df['total_liabilities'] = f_debt
            df['debt_ratio'] = (f_debt / f_asset).fillna(0) * 100
            
            # 現金流量修正：去累計化邏輯 (Q1原樣, Q2-Q4相減)
            def de_accumulate(series, dates):
                vals = series.values
                new_vals = []
                for idx, val in enumerate(vals):
                    if idx == 0 or "-03-" in dates[idx]: # 第一季不變
                        new_vals.append(val)
                    else:
                        new_vals.append(val - vals[idx-1])
                return pd.Series(new_vals, index=series.index)

            ocf_raw = safe_get(['營業活動之淨現金流入', '來自營運活動之淨現金流入'])
            df['operating_cash_flow'] = de_accumulate(ocf_raw, df['date'].tolist())
            
            icf_raw = safe_get(['投資活動之淨現金流入', '來自投資活動之淨現金流入'])
            df['free_cash_flow'] = df['operating_cash_flow'] + de_accumulate(icf_raw, df['date'].tolist())

            # 其他欄位保持原樣
            f_rev = safe_get(['營業收入', '淨收益'])
            f_gp = safe_get(['營業毛利'])
            df['gross_profit_margin'] = (f_gp / f_rev).fillna(0) * 100
            df['dividend_last_year'] = 0
            if not div_df.empty:
                last_div = div_df.sort_values('date').iloc[-1]
                for col in ['CashEarningsDistribution', 'CashDividend', 'cash_dividend']:
                    if col in last_div.index:
                        df['dividend_last_year'] = last_div[col]
                        break

            current_price = price_df['close'].iloc[-1] if not price_df.empty else 0
            return rev, df, current_price
        except Exception as e:
            print(f"⚠️ 指標計算異常: {e}")
            return None, None, 0