import os
import shutil
import subprocess
import threading

def auto_sync_to_reg_hunter():
    """
    非阻塞執行：將 financial_scan_results.csv 複製到隔壁台股法規獵人專案，
    並執行 git add, commit, push 以同步資料。
    過程中使用 try...except 捕捉所有錯誤，確保主程式不受影響。
    """
    def run_sync():
        try:
            # 1. 取得路徑
            base_dir = os.path.dirname(os.path.abspath(__file__))
            target_dir = os.path.abspath(os.path.join(base_dir, "..", "台股法規獵人"))
            source_file = os.path.join(base_dir, "financial_scan_results.csv")
            target_file = os.path.join(target_dir, "financial_scan_results.csv")

            # 確認目標目錄存在
            if not os.path.exists(target_dir):
                return
            
            # 確認來源檔案存在
            if not os.path.exists(source_file):
                return

            # 2. 複製 CSV 檔案
            shutil.copy2(source_file, target_file)

            # 3. 檢查 Git 是否有實際變更
            status = subprocess.run(
                ["git", "status", "--porcelain", "financial_scan_results.csv"], 
                cwd=target_dir, capture_output=True, text=True
            )
            # 如果沒有變更 (輸出為空)，就提早結束，避免產生空的 Commit
            if not status.stdout.strip():
                return

            # 4. 執行 Git 指令 (包含先拉取遠端更新，解決落後問題)
            from datetime import datetime
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
            commands = [
                ["git", "add", "financial_scan_results.csv"],
                ["git", "commit", "-m", f"Auto-update financial data {current_time}"],
                ["git", "pull", "--rebase", "origin", "main"], # 先抓回遠端變更 (如 GitHub Actions 的更新)
                ["git", "push", "origin", "main"]               # 再推送到雲端
            ]
            
            for cmd in commands:
                subprocess.run(
                    cmd, 
                    cwd=target_dir, 
                    capture_output=True, 
                    text=True, 
                    check=False
                )
        except Exception as e:
            # 將錯誤寫入日誌檔案，但不干擾主程式執行
            try:
                with open(os.path.join(base_dir, "sync_log.txt"), "a") as f:
                    f.write(f"[{datetime.now()}] Sync Error: {e}\n")
            except:
                pass

    # 將同步邏輯放入背景 Thread 中執行
    sync_thread = threading.Thread(target=run_sync)
    sync_thread.daemon = True  # 設定為 Daemon 執行緒，主程式結束時自動終止
    sync_thread.start()
