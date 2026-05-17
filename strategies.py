import pandas as pd

class StockStrategy:
    """台股複合式選股策略模組 - 數據對接優化版"""

    @staticmethod
    def check_growth(revenue_df, financial_df, current_price, target_growth_rate=0.3):
        try:
            if len(revenue_df) < 3 or len(financial_df) < 1: return {"match": False}
            
            # 1. 營收動能 (連續 2 個月營收YoY>20%且近月較前月高)
            rev_yoy = revenue_df['revenue_comparison_month'].iloc[-2:].tolist()
            rev_2m_ok = all(x >= 20 for x in rev_yoy)  # 連續2個月 > 20%
            
            # 近月較前月高：最後一個月 > 倒數第二個月
            rev_latest_higher = rev_yoy[1] > rev_yoy[0]
            
            rev_ok = rev_2m_ok and rev_latest_higher

            # 2. 獲利品質 (對接 DataFetcher 產出的欄位)
            # 成長股的篩選條件：
            # - 單季ROE > 5% AND 近四季ROE > 20%
            # - 單季EPS YoY > 20%
            latest_fin = financial_df.iloc[-1]
            
            roe_1q = latest_fin.get('roe_1q', 0)  # 單季ROE
            roe_4q = latest_fin.get('roe_4q', 0)  # 近四季ROE
            
            # ROE條件：單季ROE ≥ 5% AND 近四季ROE ≥ 15%
            roe_ok = (roe_1q >= 5) and (roe_4q >= 15)
            
            # EPS YoY條件：單季EPS YoY > 20%
            eps_yoy = latest_fin.get('eps_yoy_1q', 0)
            eps_yoy_ok = eps_yoy > 20
            
            eps = latest_fin.get('eps', 0)
            gross_margin = latest_fin.get('gross_profit_margin', 0)
            op_cash_flow = latest_fin.get('operating_cash_flow', 0)

            # 基礎成長判定：營收達標 + ROE符合條件 + EPS YoY符合條件 + 毛利 ≥ 20% + 有現金流入
            is_growth = (rev_ok and roe_ok and eps_yoy_ok and
                         gross_margin >= 20 and op_cash_flow > 0)

            # 3. PEG 判定 (若無 eps_yoy 則預設為 20 以進行保守計算)
            eps_4q = latest_fin.get('eps_4q_sum', 0)
            pe_ratio = current_price / eps_4q if eps_4q > 0 else 999
            
            # 使用營收年增率作為成長率替代參考進行 PEG 計算
            growth_ref = max(rev_yoy[-1], 1) 
            peg = pe_ratio / growth_ref if growth_ref > 0 else 999
            
            is_strong = is_growth and (peg < 0.75)
            return {"match": is_growth, "is_strong": is_strong}
        except:
            return {"match": False}

    @staticmethod
    def check_recession(revenue_df, financial_df):
        try:
            if len(revenue_df) < 3 or len(financial_df) < 3: return {"match": False}

            # 營收低溺 (連續三個月 YoY < 0%)
            rev_yoy = revenue_df['revenue_comparison_month'].iloc[-3:].tolist()
            rev_down = all(x < 0 for x in rev_yoy)

            latest_3_q = financial_df.iloc[-3:]
            
            # EPS 衰退判定：連續二季 EPS 年增率 (YoY) < 0% 且負值擴大
            # 即：前一季EPS YoY < 0，最新一季EPS YoY < 0，且最新一季的負值更大（更負）
            eps_yoy_prev = latest_3_q['eps_yoy_1q'].iloc[-2] if 'eps_yoy_1q' in latest_3_q.columns else 0
            eps_yoy_latest = latest_3_q['eps_yoy_1q'].iloc[-1] if 'eps_yoy_1q' in latest_3_q.columns else 0
            eps_down = (eps_yoy_prev < 0) and (eps_yoy_latest < 0) and (eps_yoy_latest < eps_yoy_prev)
            
            # 毛利率連續二季下降：前一季 > 前二季 且 最新季 < 前一季
            margin_q3 = latest_3_q['gross_profit_margin'].iloc[-3]
            margin_q2 = latest_3_q['gross_profit_margin'].iloc[-2]
            margin_q1 = latest_3_q['gross_profit_margin'].iloc[-1]
            margin_down = (margin_q3 > margin_q2) and (margin_q2 > margin_q1)
            
            # 資金壓力
            fcf_latest = latest_3_q['free_cash_flow'].iloc[-1] if 'free_cash_flow' in latest_3_q.columns else 0
            
            is_recession = rev_down and eps_down and margin_down and fcf_latest < 0
            return {"match": is_recession}
        except:
            return {"match": False}

    @staticmethod
    def check_turnaround(revenue_df, financial_df, current_price):
        try:
            if len(financial_df) < 2: return {"match": False}
            
            # 虧轉盈：上一季 EPS < 0，這一季 EPS > 0
            is_profit = financial_df['eps'].iloc[-2] < 0 and financial_df['eps'].iloc[-1] > 0
            
            # 毛利改善 (以此替代 operating_profit_yoy 以確保不改動 Fetcher 設定)
            margin_improve = financial_df['gross_profit_margin'].iloc[-1] > financial_df['gross_profit_margin'].iloc[-2]
            
            # 營收回溫：營收YoY連續二個月都 > 0
            rev_yoy_latest = revenue_df['revenue_comparison_month'].iloc[-2:].tolist()
            rev_improve = all(x > 0 for x in rev_yoy_latest)
            
            # 營運現金流 > 0
            ocf_ok = financial_df['operating_cash_flow'].iloc[-1] > 0
            
            # 股價淨值比判定 (動態計算：股價 / (權益/總股數))
            latest = financial_df.iloc[-1]
            equity = latest.get('equity', 0)
            shares = latest.get('shares', 0)
            pb = current_price / (equity / shares) if (shares > 0 and equity > 0) else 999
            pb_ok = 0 < pb < 2
            
            is_turnaround = is_profit and margin_improve and rev_improve and ocf_ok and pb_ok
            return {"match": is_turnaround}
        except:
            return {"match": False}

    @staticmethod
    def check_value(financial_df, current_price):
        try:
            if len(financial_df) < 1: return {"match": False}
            latest = financial_df.iloc[-1]
            
            # 本益比判定
            eps_4q = latest.get('eps_4q_sum', 0)
            pe = current_price / eps_4q if eps_4q != 0 else 999
            is_pe_ok = 0 < pe < 12
            
            # 股價淨值比判定 (動態計算：股價 / (權益/總股數))
            equity = latest.get('equity', 0)
            shares = latest.get('shares', 0)
            pb = current_price / (equity / shares) if (shares > 0 and equity > 0) else 999
            
            # 殖利率與負債比
            yield_rate = (latest.get('dividend_last_year', 0) / current_price) * 100 if current_price > 0 else 0
            debt_ratio = latest.get('debt_ratio', 999) # 對接 Fetcher 的 debt_ratio
            
            # 近四季ROE判定
            roe_4q = latest.get('roe_4q', 0)
            roe_ok = roe_4q > 8
            
            # 自由現金流
            fcf = latest.get('free_cash_flow', 0)
            fcf_ok = fcf > 0
            
            is_value = is_pe_ok and pb < 1.2 and yield_rate > 5 and debt_ratio < 50 and roe_ok and fcf_ok
            return {"match": is_value}
        except:
            return {"match": False}

    @staticmethod
    def check_buffett(financial_df, current_price):
        try:
            if len(financial_df) < 2: return {"match": False}
            
            latest = financial_df.iloc[-1]
            
            # 連續2年ROE>20%：檢查最近二次roe_4q都>20%
            roe_latest_2 = financial_df['roe_4q'].tail(2)
            buffett_roe_ok = all(x > 20 for x in roe_latest_2)
            
            # 本益比判定
            eps_4q = latest.get('eps_4q_sum', 0)
            pe = current_price / eps_4q if eps_4q != 0 else 999
            
            # 巴菲特指標對接修正：
            # 1. ROE (連續2年都>20% - 最近二次roe_4q都>20%)
            # 2. 負債比 (debt_ratio) < 35%
            # 3. 毛利 > 30%
            # 4. 本益比 < 15
            # 5. 自由現金流 > 0
            is_buffett = (buffett_roe_ok and 
                          latest.get('debt_ratio', 999) < 35 and 
                          latest.get('gross_profit_margin', 0) > 30 and
                          0 < pe < 15 and
                          latest.get('free_cash_flow', 0) > 0)
            return {"match": is_buffett}
        except:
            return {"match": False}