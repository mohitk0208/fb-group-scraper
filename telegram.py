from pathlib import Path
import requests


class TelegramBot:
    def __init__(self, bot_token, chat_id) -> None:
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self._payload = {
            "chat_id": chat_id,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }

    def _make_request(self, method, **kwargs):
        response = requests.post(f"{self.base_url}/{method}", **kwargs)
        return response.ok, response.json()

    def send_message(self, message):
        payload = {
            "text": message,
            **self._payload,
        }
        return self._make_request("sendMessage", data=payload)

    def send_photo(self, photo_url, message_id=None, caption=""):
        payload = {
            "photo": photo_url,
            "reply_to_message_id": message_id,
            "caption": caption,
            **self._payload,
        }
        return self._make_request("sendPhoto", data=payload)

    def send_document(self, file: Path, message_id=None, caption="" ):
        payload = {
            "reply_to_message_id": message_id,
            "caption": caption,
            **self._payload,
        }
        with file.open("rb") as f:
            resp = self._make_request(
                "sendDocument", data=payload, files={"document": f}
            )
        return resp
