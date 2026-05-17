import requests
import time
import json
import os

class TelegramNotifier:
    def __init__(self, default_token=None, default_chat_id=None):
        self.subscribers_file = "subscribers.json"
        self.default_token = default_token
        self.default_chat_id = default_chat_id

    def save_subscriber(self, token, chat_id):
        # 儲存新的訂閱者到 JSON
        subs = self.get_all_subscribers()
        subs.append({"token": token, "chat_id": chat_id})
        with open(self.subscribers_file, "w") as f:
            json.dump(subs, f)

    def get_all_subscribers(self):
        if os.path.exists(self.subscribers_file):
            with open(self.subscribers_file, "r") as f:
                return json.load(f)
        # 如果沒檔案，至少回傳開發者自己（你）
        return [{"token": self.default_token, "chat_id": self.default_chat_id}]

    def send_to_all(self, text):
        subscribers = self.get_all_subscribers()
        for sub in subscribers:
            self._send_single(sub['token'], sub['chat_id'], text)

    def _send_single(self, token, chat_id, text):
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        for attempt in range(3):
            try:
                r = requests.post(url, data=payload, timeout=15)
                r.raise_for_status()
                break
            except:
                time.sleep(2)