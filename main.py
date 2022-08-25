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
    leeway = int(getenv("LEEWAY", 2))
    look_back = (
        datetime.now() - timedelta(minutes=int(getenv("LOOKBACK", 30)) + leeway)
    ).timestamp()

    facebook_client = Facebook(COOKIES)

    scraper = FacebookScraper(facebook_client, getenv("FACEBOOK_GROUP_ID"))
    bot = TelegramBot(getenv("TELEGRAM_BOT_TOKEN"), getenv("TELEGRAM_CHAT_ID"))

    posts = scraper.get_new_posts(look_back)

    for post in posts:
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
                    bot.send_photo(attachment, caption=message)
                elif attachment_type == "file":
                    bot.send_document(attachment, caption=message)
                else:
                    bot.send_message(message)
            else:
                ok, response = bot.send_message(message)
                if not ok:
                    print(response)
                    continue

                if attachment_type == "image":
                    bot.send_photo(attachment, message_id=response["result"]["message_id"])
                elif attachment_type == "file":
                    bot.send_document(attachment,message_id=response["result"]["message_id"])
        else:
            bot.send_message(f"{post.formatted_time}\n{post.url}")


if __name__ == "__main__":
    main()
