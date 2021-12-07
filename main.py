#!/usr/bin/env python3

import datetime
import re
from os import getenv

import requests
import facebook_scraper

cookies = {
    "c_user": getenv("c_user"),
    "datr": getenv("datr"),
    "fr": getenv("fr"),
    "sb": getenv("sb"),
    "xs": getenv("xs"),
}


class TelegramBot:
    def __init__(self, bot_token, chat_id) -> None:
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.chat_id = chat_id

    def send_message(self, message):
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        response = requests.post(f"{self.base_url}/sendMessage", data=payload)
        return response.json()

    def send_photo(self, photo_url, message):
        payload = {
            "chat_id": self.chat_id,
            "photo": photo_url,
            "caption": message,
            "parse_mode": "HTML",
        }
        response = requests.post(f"{self.base_url}/sendPhoto", data=payload)
        return response.json()

    def send_video(self, video_url, message):
        payload = {
            "chat_id": self.chat_id,
            "video": video_url,
            "caption": message,
            "parse_mode": "HTML",
        }
        response = requests.post(f"{self.base_url}/sendVideo", data=payload)
        return response.json()

    def send_media_group(self, media_entries):
        payload = {
            "chat_id": self.chat_id,
            "media": media_entries,
        }
        response = requests.post(f"{self.base_url}/sendMediaGroup", data=payload)
        return response.json()


def format_post(post):
    post_url = post["post_url"].replace("m.facebook.com", "www.facebook.com")
    message = (
        f"<a href='{post_url}'>{post.get('header', 'New post by '+ post['username'])}</a>\n"
        f"<b>Time:</b> {post['time']}\n"
        f"{post['post_text']}"
    )

    # extract links from post
    links = [post["link"]]
    for link in post["links"]:
        links.append(link["text"])
    links = set(links)
    try:
        links.remove(None)
    except KeyError:
        pass
    if links:
        message += "\nLinks:\n"
        message += "\n\n".join(links)

    return message


if __name__ == "__main__":

    bot = TelegramBot(
        bot_token=getenv("TELEGRAM_BOT_TOKEN"),
        chat_id=getenv("TELEGRAM_CHAT_ID"),
    )

    time_offset = (
        datetime.datetime.utcnow()
        - datetime.timedelta(hours=int(getenv("TIME_OFFSET", 3)), minutes=2)
    ).timestamp()

    # facebook_scraper.enable_logging()
    try:
        _posts = facebook_scraper.get_posts(
            group=getenv("GROUP_ID"), cookies=cookies, options={"progress": True}
        )
    except facebook_scraper.exceptions.LoginError:
        bot.send_message("Login failed. Someone stole your cookies.")
        exit(1)

    posts = []
    for post in _posts:
        if post["timestamp"] < time_offset:
            break
        posts.append(post)

    for post in _posts[::-1]:
        if post["image"]:
            if len(post["images"]) == 1:
                resp = bot.send_photo(post["image"], format_post(post))
                print(
                    {
                        "result": resp["result"],
                        "message_id": resp.get("result", {}).get("message_id"),
                    }
                )
            else:
                media_entries = [
                    {"type": "photo", "media": image} for image in post["images"]
                ]
                if post["video"]:
                    media_entries.append({"type": "video", "media": post["video"]})
                resp = bot.send_media_group(media_entries)
                print(
                    {
                        "result": resp["result"],
                        "message_id": resp.get("result", {}).get("message_id"),
                    }
                )
                resp = bot.send_message(format_post(post))
                print(
                    {
                        "result": resp["result"],
                        "message_id": resp.get("result", {}).get("message_id"),
                    }
                )
        elif post["video"]:
            resp = bot.send_video(post["video"], format_post(post))
            print(
                {
                    "result": resp["result"],
                    "message_id": resp.get("result", {}).get("message_id"),
                }
            )
        else:
            resp = bot.send_message(format_post(post))
            print(
                {
                    "result": resp["result"],
                    "message_id": resp.get("result", {}).get("message_id"),
                }
            )
