#!/usr/bin/env python3

import contextlib
from datetime import datetime, timedelta
import json
from os import getenv
from urllib.parse import urlparse, parse_qs, unquote
from zoneinfo import ZoneInfo
from pathlib import Path

from bs4 import BeautifulSoup
import requests

FB_BASE_URL = "https://mbasic.facebook.com"

# ipv6 is painful to work with
requests.packages.urllib3.util.connection.HAS_IPV6 = False

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
        return response.json()

    def send_message(self, message):
        payload = {
            "text": message,
            **self._payload,
        }
        return self._make_request("sendMessage", data=payload)

    def send_photo(self, photo_url, message):
        payload = {
            "photo": photo_url,
            "caption": message,
            **self._payload,
        }
        return self._make_request("sendPhoto", data=payload)

    def send_document(self, file:Path, message):
        payload = {
            "caption": message,
            **self._payload,
        }
        with file.open("rb") as f:
            resp = self._make_request(
                "sendDocument", data=payload, files={"document": f}
            )
        return resp


class FacebookScraper:
    def __init__(self, cookies, group_id):
        self.session = requests.Session()
        self.session.cookies = requests.utils.cookiejar_from_dict(cookies)
        self.group_id = group_id
        self.group_url = f"{FB_BASE_URL}/groups/{group_id}"
        self.downloads_folder = Path(__file__).parent / "downloads"

    def fetch_new_posts(self, look_back):
        page = self.group_url
        to_fetch = 3  # look ahead a few pages so that we dont miss out new posts
        posts = []
        while to_fetch > 0:
            response = self.session.get(page)
            soup = BeautifulSoup(response.text, "lxml")
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
                + soup.select_one("#m_group_stories_container>div:nth-child(2)>a")[
                    "href"
                ]
            )

            if posts[-1]["time"] < look_back:
                to_fetch -= 1

            new_posts = []
            for post in posts:
                if post["time"] < look_back:
                    break
                new_posts.append(post)
        return new_posts[::-1]

    @staticmethod
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
                rec.append(FacebookScraper.get_text(tag))
        rec = filter(None, rec)  # remove empty values
        # FIXME: instead of flattening children flatten siblings if any one of them is a span
        return "".join(rec) if soup.name == "span" else "\n".join(rec)

    def parse_post(self, post_id, post_time):
        post_url = f"{self.group_url}/permalink/{post_id}"
        # print(post_url)
        response = self.session.get(post_url)
        post = BeautifulSoup(response.text, "lxml").find(
            attrs={"data-ft": '{"tn":"*s"}'}
        )

        parsed_post = {
            "id": post_id,
            "post_url": post_url,
            "time": (
                datetime.fromtimestamp(
                    post_time,
                    tz=ZoneInfo("UTC"),
                )
                .astimezone(ZoneInfo("Asia/Kolkata"))
                .strftime("%a, %b %-d %-I:%M %p")
            ),
            "head": post.previous_sibling.select_one(
                "table>tbody>tr>td:nth-child(2)>div>h3"
            ).text,
            "body": self.get_text(post),
            # "content": post,
        }

        if attachment := post.next_sibling:
            _link = attachment.find("a")
            link = _link["href"]
            if link.startswith("http"):
                try:
                    parsed_link = urlparse(link)
                    link_qs = parse_qs(parsed_link.query)
                    link = link_qs["u"][0]
                    if "lookaside.fbsbx.com" in link:
                        filename = unquote(urlparse(link).path.split("/")[-1])
                        file = self.downloads_folder / filename
                        file.write_bytes((self.session.get(link).content))
                        parsed_post["file"] = file
                    else:
                        parsed_post["link"] = link
                        parsed_post["link_text"] = next(_link.stripped_strings)
                except Exception as e:
                    print(e)
                    parsed_post["link"] = link
                    parsed_post["link_text"] = next(_link.stripped_strings)
            else:
                parsed_post["image"] = attachment.find("img")["src"]
        return parsed_post

    def get_posts(self, look_back):
        latest_posts = self.fetch_new_posts(look_back)
        parsed_posts = []
        for post in latest_posts:
            try:
                parsed_posts.append(self.parse_post(post["id"], post["time"]))
            except Exception as e:
                print(e)
        return parsed_posts


def format_message_body(post):
    message = (
        f"<a href=\"{post['post_url']}\">{post['head']}</a>\n"
        f"<b>Time:</b> {post['time']}\n\n"
        f"{post['body']}"
    )
    if link := post.get("link"):
        message += f"\n<a href='{link}'>{post['link_text']}</a>"
    return message


def main():
    COOKIES = {
        "c_user": getenv("c_user"),
        "xs": getenv("xs"),
    }
    look_back = (
        datetime.now() - timedelta(minutes=int(getenv("LOOKBACK", 30)))
    ).timestamp()

    scraper = FacebookScraper(COOKIES, getenv("GROUP_ID"))
    bot = TelegramBot(getenv("TELEGRAM_BOT_TOKEN"), getenv("TELEGRAM_CHAT_ID"))

    posts = scraper.get_posts(look_back)

    for post in posts:
        try:
            message_body = format_message_body(post)
            if image := post.get("image"):
                response = bot.send_photo(image, message_body)
            elif file := post.get("file"):
                response = bot.send_document(file, message_body)
            else:
                response = bot.send_message(message_body)
            print(response)
        except Exception as e:
            print(e)


if __name__ == "__main__":
    main()
