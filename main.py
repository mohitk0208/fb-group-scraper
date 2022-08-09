#!/usr/bin/env python3

from datetime import datetime, timedelta
import json
from os import getenv
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup as bs
import requests

FB_BASE_URL = "https://mbasic.facebook.com"


class TelegramBot:
    def __init__(self, bot_token, chat_id) -> None:
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.chat_id = chat_id
        self._payload = {
            "chat_id": chat_id,
            "parse_mode": "HTML",
        }

    def _make_request(self, method, payload):
        response = requests.post(f"{self.base_url}/{method}", data=payload)
        return response.json()

    def send_message(self, message):
        payload = {
            "text": message,
            **self._payload,
        }
        return self._make_request("sendMessage", payload)

    def send_photo(self, photo_url, message):
        payload = {
            "photo": photo_url,
            "caption": message,
            **self._payload,
        }
        return self._make_request("sendPhoto", payload)


def format_post(post):
    message = (
        f"<a href=\"{post['post_url']}\">{post['head']}</a>\n"
        f"<b>Time:</b> {post['time']}\n"
        f"{post['body']}"
    )

    if link := post.get("link"):
        message += "\nLinks:\n"
        message += f"<a href='{link}'>{post['link_text']}</a>"
    return message


def get_text(soup):
    if soup is None:
        return ""
    if isinstance(soup, str):
        return soup
    if soup.name == "a":
        return soup["href"]
    rec = [get_text(x) for x in soup.contents]
    return "".join(rec) if soup.name == "span" else "\n".join(rec)


def main():
    GROUP_ID = getenv("GROUP_ID")
    COOKIES = {
        "c_user": getenv("c_user"),
        "datr": getenv("datr"),
        "fr": getenv("fr"),
        "sb": getenv("sb"),
        "xs": getenv("xs"),
    }

    INTERVAL = int(getenv("INTERVAL", 30))

    bot = TelegramBot(
        bot_token=getenv("TELEGRAM_BOT_TOKEN"),
        chat_id=getenv("TELEGRAM_CHAT_ID"),
    )

    now = (datetime.now() - timedelta(minutes=INTERVAL)).timestamp()

    page = f"{FB_BASE_URL}/groups/{GROUP_ID}"
    session = requests.Session()
    session.cookies = requests.utils.cookiejar_from_dict(COOKIES)
    posts = []

    to_fetch = 3

    while to_fetch > 0:
        response = session.get(page)
        soup = bs(response.text, "lxml")
        for post in soup.select("#m_group_stories_container>div>div"):
            _p = json.loads(post.get("data-ft"))
            posts.append(
                {
                    "id": _p["top_level_post_id"],
                    "time": next(iter(_p["page_insights"].values()))["post_context"][
                        "publish_time"
                    ],
                }
            )
        posts.sort(key=lambda x: x["time"], reverse=True)
        page = (
            FB_BASE_URL
            + soup.select_one("#m_group_stories_container>div:nth-child(2)>a")["href"]
        )

        if posts[-1]["time"] < now:
            to_fetch -= 1

    for i in range(len(posts)):
        if posts[i]["time"] < now:
            break
    posts = posts[: i + 1]

    parsed_posts = []
    for _post in posts:
        post_url = f"{FB_BASE_URL}/groups/{GROUP_ID}/permalink/{_post['id']}"
        # print(post_url)
        response = session.get(post_url)
        post = bs(response.text, "lxml").select_one("#m_story_permalink_view")

        content = post.find(attrs={"data-ft": '{"tn":"*s"}'})

        _pos = {
            "id": _post["id"],
            "post_url" : post_url,
            "time": datetime.fromtimestamp(
                _post["time"], tz=ZoneInfo("UTC")
            ).astimezone(ZoneInfo("Asia/Kolkata")),
            "head": content.previous_sibling.select_one(
                "table>tbody>tr>td:nth-child(2)>div>h3"
            ).text,
            "body": get_text(content),
            "content": content,
        }

        if footer := post.find(attrs={"data-ft": '{"tn":"H"}'}):
            _link = footer.find("a")
            link = _link["href"]
            if link.startswith("http"):
                _pos["link"] = link
                _pos["link_text"] = _link.text
            else:
                _pos["image"] = footer.find("img")["src"]

        parsed_posts.append(_pos)

    print(parsed_posts)

    for post in parsed_posts:
        try:
            if post.get("image"):
                bot.send_photo(post["image"], format_post(post))
            else:
                bot.send_message(format_post(post))
        except Exception as e:
            print(e)

if __name__ == "__main__":
    main()