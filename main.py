#!/usr/bin/env python3
import requests
from os import getenv
from datetime import datetime, timedelta

from telegram import TelegramBot
from facebook import FacebookScraper, Facebook

# ipv6 is painful to work with
requests.packages.urllib3.util.connection.HAS_IPV6 = False


def main():
    COOKIES = {
        "c_user": getenv("c_user"),
        "xs": getenv("xs"),
    }

    last_post_time = None
    try:
        with open("session.txt", "r") as f:
            last_post_time = datetime.fromtimestamp(float(f.read().strip()))
    except Exception as e:
        print(e)

    if last_post_time is not None:
        extra_microseconds = timedelta(milliseconds=100) # adding extra time so same post is not fetched again
        look_back = (last_post_time + extra_microseconds ).timestamp()
    else:
        look_back = (
            datetime.now() - timedelta(minutes=int(getenv("LOOKBACK", 30)))
        ).timestamp()

    facebook_client = Facebook(COOKIES)

    scraper = FacebookScraper(facebook_client, getenv("FACEBOOK_GROUP_ID"))
    bot = TelegramBot(getenv("TELEGRAM_BOT_TOKEN"), getenv("TELEGRAM_CHAT_ID"))

    posts = scraper.get_new_posts(look_back)

    last_sent_post_time = None

    for post in posts:
        ok, response = False, None
        if post.is_post_parsed:
            message = post.get_formatted_message_body_for_telegram()
            if len(message) > 4095:
                message = (
                        f"{post.formatted_time}\n{post.url}"
                        f"Message TOO large to display \n "
                        f'<a href="{post.url}" >view it on facebook</a>'
                    )


            attachment_type = post.attachment_type
            attachment = post.attachment
            if len(message) < 1024:
                if attachment_type == "image":
                    ok, response = bot.send_photo(attachment, caption=message)
                elif attachment_type == "file":
                    ok, response = bot.send_document(attachment, caption=message)
                else:
                    ok, response = bot.send_message(message)
            else:
                ok, response = bot.send_message(message)
                if not ok:
                    print(response)
                    continue

                if attachment_type == "image":
                    ok, response = bot.send_photo(attachment, message_id=response["result"]["message_id"])
                elif attachment_type == "file":
                    ok, response = bot.send_document(attachment,message_id=response["result"]["message_id"])
        else:
            ok, response = bot.send_message(f"{post.formatted_time}\n{post.url}")

        if ok:
            last_sent_post_time = post.publish_time

    if last_sent_post_time is not None:
        with open("session.txt", "w") as f:
            f.write(str(last_sent_post_time))


if __name__ == "__main__":
    main()
