#!/usr/bin/env python3
import requests
from os import getenv
from datetime import datetime, timedelta

# ipv6 is painful to work with
requests.packages.urllib3.util.connection.HAS_IPV6 = False

from telegram import TelegramBot
from facebook import FacebookScraper, FacebookPost


def format_message_body(post:FacebookPost):
    message = (
        f"<a href=\"{post.url}\">{post.header}</a>\n"
        f"<b>Time:</b> {post.formatted_time}\n\n"
        f"{post.body}"
    )
    if post.attachment_type == "link":
        message += (
            f"\n\n<a href='{post.attachment}'>{post.attachment_caption}</a>"
        )
    return message


def main():
    COOKIES = {
        "c_user": getenv("c_user"),
        "xs": getenv("xs"),
    }
    look_back = (
        datetime.now() - timedelta(minutes=int(getenv("LOOKBACK", 30)))
    ).timestamp()               # means LOOKBACK mins before from now

    scraper = FacebookScraper(COOKIES, getenv("GROUP_ID"))
    bot = TelegramBot(getenv("TELEGRAM_BOT_TOKEN"), getenv("TELEGRAM_CHAT_ID"))

    posts = scraper.get_posts(look_back)

    for post in posts:
        if post.is_post_parsed:
            message = format_message_body(post)
            if len(message) > 4095:
                message = f'{post.formatted_time}\n{post.url}'

            ok, response = bot.send_message(message)
            if not ok:
                print(response)
                continue

            attachment_type = post.attachment_type
            attachment = post.attachment
            if attachment_type == "image":
                bot.send_photo(attachment, response["result"]["message_id"])
            elif attachment_type == "file":
                bot.send_document(attachment, response["result"]["message_id"])
        else:
            bot.send_message(f'{post.formatted_time}\n{post.url}')


if __name__ == "__main__":
    main()
