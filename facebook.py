import requests
from pathlib import Path
from bs4 import BeautifulSoup
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, parse_qs, unquote, urljoin


FB_BASE_URL = "https://mbasic.facebook.com"


class Facebook:
    def __init__(self, cookies: dict):
        self.default_headers = {
            "Accept": "*/*",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Host": "mbasic.facebook.com",
            "Pragma": "no-cache",
            "Referer": "https://mbasic.facebook.com/home.php",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "User-Agent": "Mozilla/5.0 (Android 12; Mobile; rv:104.0) Gecko/104.0 Firefox/104.0",
        }
        self.session = requests.Session()
        self.session.headers.update(self.default_headers)
        self.session.cookies = requests.utils.cookiejar_from_dict(cookies)


class FacebookPost:
    def __init__(self, client: Facebook, parsed_post_meta_data):
        self.session = client.session
        self.id = parsed_post_meta_data["top_level_post_id"]
        self.publish_time = next(iter(parsed_post_meta_data["page_insights"].values()))[
            "post_context"
        ]["publish_time"]
        self.group_id = parsed_post_meta_data["page_id"]  # it is the group id
        self.group_url = f"{FB_BASE_URL}/groups/{self.group_id}"
        self.downloads_folder = Path(__file__).parent / "downloads"
        self.is_post_parsed = False
        self.url = f"{self.group_url}/permalink/{self.id}"
        self.formatted_time = (
            datetime.fromtimestamp(
                self.publish_time,
                tz=ZoneInfo("UTC"),
            )
            .astimezone(ZoneInfo("Asia/Kolkata"))
            .strftime("%a, %b %-d %-I:%M %p")
        )
        self.header = None
        self.posted_by = None
        self.posted_by_url = None
        self.event = None
        self.group_name = None
        self.body = None
        self.attachment_type = None
        self.attachment = None
        self.attachment_caption = None
        self.parse_post()

    def get_text(self, soup) -> str:
        # hacky logic to flatten out deeply nested facebook post body
        if soup is None:
            return ""
        if soup.name == "a":
            return "".join(soup.stripped_strings)  # urls won't have nested elements
        rec = []
        for tag in soup.contents:
            if isinstance(tag, str):
                rec.append(tag.strip())
            elif tag.name in ("h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"):
                rec.append(f"<b>{self.get_text(tag)}</b>")
            elif tag.name in ("em", "i"):
                rec.append(f"<i>{self.get_text(tag)}</i>")
            else:
                rec.append(self.get_text(tag))
        rec = filter(None, rec)  # remove empty values
        # FIXME: instead of flattening children flatten siblings if any one of them is a span
        return "".join(rec) if soup.name == "span" else "\n".join(rec)

    def parse_post(self):

        try:
            response = self.session.get(self.url)
            post = BeautifulSoup(response.text, "xml").find(
                attrs={"data-ft": '{"tn":"*s"}'}
            )
            # parsed_post["content"] = post
            head = post.previous_sibling.select_one(
                "table>tbody>tr>td:nth-child(2)>div>h3"
            )
            self.header = head.text
            self.posted_by = head.select("strong>a")[0].text
            self.posted_by_url = self.remove_url_query_params(
                f'{FB_BASE_URL}{head.select("strong>a")[0]["href"]}'
            )
            self.event = head.find(text=True, recursive=False) or " &gt; "
            self.group_name = head.select("strong>a")[1].text

            self.body = self.get_text(post)

            if attachment_container := post.next_sibling:
                attachment = attachment_container.find("a")
                attachment_link: str = attachment["href"]
                if attachment_link.startswith("http"):
                    # external link attached
                    self.attachment_type = "link"
                    self.attachment = attachment_link
                    self.attachment_caption = next(attachment.stripped_strings, "")

                    # get actual link from lm.facebook.com/l.php
                    parsed_link = urlparse(attachment_link)
                    link_qs = parse_qs(parsed_link.query)
                    actual_link = link_qs["u"][0]
                    # TODO: remove facebook trackers from actual link
                    self.attachment = actual_link

                    if "lookaside.fbsbx.com" in actual_link:
                        # attachment is a file
                        filename = unquote(urlparse(actual_link).path.split("/")[-1])
                        file = self.downloads_folder / filename
                        file.write_bytes((self.session.get(actual_link).content))
                        self.attachment_type = "file"
                        self.attachment = file
                elif attachment_link.startswith("/photo"):
                    # the attachment is an image
                    self.attachment_type = "image"
                    try:
                        image_url = FB_BASE_URL + attachment_link
                        image_id = parse_qs(urlparse(image_url).query)["fbid"][0]
                        redirect_url = self.session.get(
                            f"{FB_BASE_URL}/photo/view_full_size/?fbid={image_id}"
                        )
                        redirect_soup = BeautifulSoup(redirect_url.content, "xml")
                        self.attachment = redirect_soup.find("a")["href"]
                    except Exception as e:
                        print(e)
                        self.attachment = attachment_container.find("img")["src"]

            self.is_post_parsed = True
        except Exception as e:
            print(e)

    def get_formatted_message_body_for_telegram(self) -> str:
        message = (
            f'<a href="{self.posted_by_url}">{self.posted_by}</a>'
            f"{self.event}"
            f'<b><a href="{self.group_url}">{self.group_name}</a></b>\n'
            f"<code>{self.formatted_time}</code>\n\n"
            f"{self.body}\n\n"
        )
        if self.attachment_type == "link":
            message += f"<a href='{self.attachment}'>{self.attachment_caption}</a>\n"
        message += f'<a href="{self.url}">view on facebook</a>'
        return message

    def remove_url_query_params(self, url: str):
        return urljoin(url, urlparse(url).path)


class FacebookScraper:
    def __init__(self, client: Facebook, group_id: str):
        self.client = client
        self.session = client.session
        self.group_id = group_id
        self.group_url = f"{FB_BASE_URL}/groups/{group_id}"

    def get_posts_till_lookback(
        self, num_of_after_pages: int, look_back: int
    ) -> list[FacebookPost]:
        """
        Fetch posts from facebook group

        Parameters
        ----------
        num_of_after_pages : int
            number of extra pages to fetch after posts till lookback have been fetched.
        look_back : int
            time in minutes.

        Returns
        -------
        list[FacebookPost]
        """
        page = self.group_url
        posts: list[FacebookPost] = list()
        least_recent_post_time = float("inf")

        while num_of_after_pages > 0:

            response = self.session.get(page)
            soup = BeautifulSoup(response.text, "xml")
            least_recent_post_time = float("inf")

            for post in soup.select("#m_group_stories_container>div>div"):
                parsed_post = json.loads(post.get("data-ft"))
                post = FacebookPost(self.client, parsed_post)
                posts.append(post)
                least_recent_post_time = min(least_recent_post_time, post.publish_time)

            page = (
                FB_BASE_URL
                + soup.select_one("#m_group_stories_container>div:nth-child(2)>a")[
                    "href"
                ]
            )

            if least_recent_post_time < look_back:
                num_of_after_pages -= 1

        posts.sort(key=lambda x: x.publish_time, reverse=True)
        return posts

    def get_new_posts(self, look_back: int) -> list[FacebookPost]:

        posts = self.get_posts_till_lookback(3, look_back)
        new_posts = list(filter(lambda x: x.publish_time >= look_back, posts))

        return new_posts[::-1]
