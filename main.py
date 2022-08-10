#!/usr/bin/env python3

from datetime import datetime, timedelta
import json
from os import getenv
from urllib.parse import urlparse, parse_qs
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
            "disable_web_page_preview": "true",
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


def format_message_body(post):
    message = (
        f"<a href=\"{post['post_url']}\">{post['head']}</a>\n"
        f"<b>Time:</b> {post['time']}\n\n"
        f"{post['body']}"
    )
    if link := post.get("link"):
        message += f"\n\n<a href='{link}'>{post['link_text']}</a>"
    return message


def get_text(soup):
    # hacky logic to flatten out deeply nested facebook post body
    if soup is None:
        return ""
    if soup.name == "a":
        return "".join(soup.stripped_strings)  # urls won't have nested elements

    rec = []
    for tag in soup.contents:
        if isinstance(tag, str):
            rec.append(tag.strip())
        else:
            rec.append(get_text(tag))
    rec = filter(None, rec)  # remove empty values
    # FIXME: instead of flattening children flatten siblings if any one of them is a span
    return "".join(rec) if soup.name == "span" else "\n".join(rec)


def main():
    GROUP_ID = getenv("GROUP_ID")
    INTERVAL = int(getenv("INTERVAL", 30))
    COOKIES = {
        "c_user": getenv("c_user"),
        "datr": getenv("datr"),
        "fr": getenv("fr"),
        "sb": getenv("sb"),
        "xs": getenv("xs"),
    }

    last_fetched = (datetime.now() - timedelta(minutes=INTERVAL)).timestamp()
    session = requests.Session()
    session.cookies = requests.utils.cookiejar_from_dict(COOKIES)

    page = f"{FB_BASE_URL}/groups/{GROUP_ID}"
    to_fetch = 3  # look ahead a few pages so that we dont miss out new posts
    posts = []
    while to_fetch > 0:
        response = session.get(page)
        soup = bs(response.text, "lxml")
        for post in soup.select("#m_group_stories_container>div>div"):
            parsed_post = json.loads(post.get("data-ft"))
            posts.append(
                {
                    "id": parsed_post["top_level_post_id"],
                    "time": next(iter(parsed_post["page_insights"].values()))[
                        "post_context"
                    ]["publish_time"],
                }
            )
        posts.sort(key=lambda x: x["time"], reverse=True)
        page = (
            FB_BASE_URL
            + soup.select_one("#m_group_stories_container>div:nth-child(2)>a")["href"]
        )

        if posts[-1]["time"] < last_fetched:
            to_fetch -= 1

    new_posts = []
    for post in posts:
        if post["time"] < last_fetched:
            break
        new_posts.append(post)

    parsed_posts = []
    for _post in new_posts:
        post_url = f"{FB_BASE_URL}/groups/{GROUP_ID}/permalink/{_post['id']}"
        # print(post_url)
        response = session.get(post_url)
        post = bs(response.text, "lxml").select_one("#m_story_permalink_view")

        content = post.find(attrs={"data-ft": '{"tn":"*s"}'})

        parsed_post = {
            "id": _post["id"],
            "post_url": post_url,
            "time": (
                datetime.fromtimestamp(
                    _post["time"],
                    tz=ZoneInfo("UTC"),
                )
                .astimezone(ZoneInfo("Asia/Kolkata"))
                .strftime("%a, %b %-m %-I:%M %p")
            ),
            "head": content.previous_sibling.select_one(
                "table>tbody>tr>td:nth-child(2)>div>h3"
            ).text,
            "body": get_text(content),
            # "text": list(content.stripped_strings),
            "content": content,
        }

        if footer := content.next_sibling:
            _link = footer.find("a")
            link = _link["href"]
            if link.startswith("http"):
                if "lm.facebook" in link:
                    parsed_link = parse_qs(urlparse(link).query)
                    try:
                        link = parsed_link["u"][0]
                    except (KeyError, IndexError):
                        link = ""
                parsed_post["link"] = link
                parsed_post["link_text"] = next(_link.stripped_strings)
            else:
                parsed_post["image"] = footer.find("img")["src"]

        parsed_posts.append(parsed_post)

    # print(parsed_posts)

    bot = TelegramBot(
        bot_token=getenv("TELEGRAM_BOT_TOKEN"),
        chat_id=getenv("TELEGRAM_CHAT_ID"),
    )

    for post in parsed_posts[::-1]:
        try:
            message_body = format_message_body(post)
            if post.get("image"):
                bot.send_photo(post["image"], message_body)
            else:
                bot.send_message(message_body)
        except Exception as e:
            print(e)


if __name__ == "__main__":
    main()
