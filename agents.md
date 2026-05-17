# AGENTS.md - Instructions for AI Coding Agents

## Project Overview
這是一個使用 Python 開發的台股相關應用程式。目前正在開發「台股財報獵人app」

## Developer Background
- 我是完全不懂寫程式的新手。
- 我全部使用中文與 AI 溝通。

## Strict Rules for All AI Agents (Must Follow)

1. **Precise Modification Only**  
   Only modify the exact parts that the user explicitly asks for in this request. 
   Do not make any changes to other unrelated code, including the text and UI on the interface.

2. **Data & API Integrity (資料與 API 完整性) [Strict Rule]**  
   For all Taiwan stock related data (CSV files, FinMind, Fugle, Yahoo Finance, or any other API), it is **STRICTLY FORBIDDEN** to modify any column names, variable names, or field definitions.  
   中文準則：嚴禁擅自更改任何台股相關的資料欄位名稱或變數名稱。  
   例如：不可把「收盤價」改成「close」、「close_price」；不可把「成交量」改成「volume」；不可把「開盤價」改成「open」等。  
   如果修改真的需要涉及資料欄位或變數名稱，必須先用中文清楚說明你要改什麼，並等待我確認（Confirm）後才可執行。

3. 若有需要測試搜尋結果，可把搜尋標的暫時改成只搜2、3支股票，以節省finmind額度，測完再改回來。