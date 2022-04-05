#!/usr/bin/env python3

import datetime
import json
from os import getenv
from bs4 import BeautifulSoup as bs

import requests
import facebook_scraper

COOKIES = {
    "c_user": getenv("c_user"),
    "datr": getenv("datr"),
    "fr": getenv("fr"),
    "sb": getenv("sb"),
    "xs": getenv("xs"),
}
GROUP_ID = getenv("GROUP_ID")

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

    def send_video(self, video_url, message):
        payload = {
            "video": video_url,
            "caption": message,
            **self._payload,
        }
        return self._make_request("sendVideo", payload)

    def send_media_group(self, media_entries):
        payload = {
            "chat_id": self.chat_id,
            "media": media_entries,
        }
        return self._make_request("sendMediaGroup", payload)


def format_post(post):
    time = post['time'] + datetime.timedelta(hours=5, minutes=30)
    post_url = post["original_request_url"]
    message = (
        f"<a href='{post_url}'>{post.get('header', 'New post by '+ post['username'])}</a>\n"
        f"<b>Time:</b> {time}\n"
        f"{post['text'] or post['post_text'] or post['shared_text'] or post['original_text']}"
    )

    # extract links from post
    links = {post["link"],}
    for link in post["links"]:
        links.add(link["text"])
    links.discard(None)
    if links:
        message += "\nLinks:\n"
        message += "\n\n".join(links)
    return message


def fetch_posts(group_id):
    session = requests.Session()
    session.cookies = requests.utils.cookiejar_from_dict(COOKIES)
    response = session.get(f"{FB_BASE_URL}/groups/{group_id}")
    if not response.ok:
        return []
    soup = bs(response.text, "lxml")
    posts = soup.select("#m_group_stories_container>div>div")
    post_ids = []
    for post in posts:
        post_data_ft = json.loads(post.get("data-ft"))
        post_ids.append(post_data_ft["top_level_post_id"])
    return post_ids


if __name__ == "__main__":

    bot = TelegramBot(
        bot_token=getenv("TELEGRAM_BOT_TOKEN"),
        chat_id=getenv("TELEGRAM_CHAT_ID"),
    )

    try:
        with open("session.txt", "r") as f:
            old_post_ids = set(f.read().splitlines())
    except (FileNotFoundError, TypeError) as e:
        print(e)
        old_post_ids = set()

    all_post_ids = set(fetch_posts(getenv("GROUP_ID"))) | old_post_ids
    new_post_ids = all_post_ids - old_post_ids

    new_post_urls = [
        f"{FB_BASE_URL}/groups/{GROUP_ID}/permalink/{post_id}"
        for post_id in new_post_ids
    ]

    # facebook_scraper.enable_logging()
    try:
        _posts = facebook_scraper.get_posts(
            cookies=COOKIES,
            post_urls=new_post_urls,
        )
    except facebook_scraper.exceptions.LoginError:
        bot.send_message("Login failed. Someone stole your cookies.")
        exit(1)

    for post in list(_posts)[::-1]:
        try:
            if post["image"]:
                if len(post["images"]) == 1:
                    bot.send_photo(post["image"], format_post(post))
                else:
                    media_entries = [
                        {"type": "photo", "media": image} for image in post["images"]
                    ]
                    if post["video"]:
                        media_entries.append({"type": "video", "media": post["video"]})
                    bot.send_media_group(media_entries)
                    bot.send_message(format_post(post))
            elif post["image_lowquality"]:
                bot.send_photo(post["image_lowquality"], format_post(post))
            elif post["video"]:
                bot.send_video(post["video"], format_post(post))
            else:
                bot.send_message(format_post(post))
            if post["post_id"]:
                last_post_id = post["post_id"]
        except Exception as e:
            print(e)
            continue

    with open("session.txt", "w+") as f:
        f.write("\n".join(all_post_ids))
