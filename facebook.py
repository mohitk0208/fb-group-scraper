import requests
from pathlib import Path
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo



class FacebookScraper:
    def __init__(self, cookies, group_id, fb_base_url=None):
        self.FB_BASE_URL = fb_base_url if fb_base_url else "https://mbasic.facebook.com"
        self.session = requests.Session()
        self.session.cookies = requests.utils.cookiejar_from_dict(cookies)
        self.group_id = group_id
        self.group_url = f"{self.FB_BASE_URL}/groups/{group_id}"
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
                self.FB_BASE_URL
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

        parsed_post = {
            "parse_complete": False,
            "id": post_id,
            "url": post_url,
            "time": (
                datetime.fromtimestamp(
                    post_time,
                    tz=ZoneInfo("UTC"),
                )
                .astimezone(ZoneInfo("Asia/Kolkata"))
                .strftime("%a, %b %-d %-I:%M %p")
            ),
        }

        try:
            response = self.session.get(post_url)
            post = BeautifulSoup(response.text, "lxml").find(
                attrs={"data-ft": '{"tn":"*s"}'}
            )
            # parsed_post["content"] = post
            parsed_post["header"] = post.previous_sibling.select_one(
                "table>tbody>tr>td:nth-child(2)>div>h3"
            ).text
            parsed_post["body"] = self.get_text(post)

            if attachment_container := post.next_sibling:
                attachment = attachment_container.find("a")
                attachment_link: str = attachment["href"]
                if attachment_link.startswith("http"):
                    # external link attached
                    parsed_post["attachment_type"] = "link"
                    parsed_post["attachment"] = attachment_link
                    parsed_post["attachment_caption"] = next(
                        attachment.stripped_strings, ""
                    )
                    # get actual link from lm.facebook.com/l.php
                    parsed_link = urlparse(attachment_link)
                    link_qs = parse_qs(parsed_link.query)
                    actual_link = link_qs["u"][0]
                    # TODO: remove facebook trackers from actual link
                    parsed_post["attachment"] = actual_link
                    if "lookaside.fbsbx.com" in actual_link:
                        # attachment is a file
                        filename = unquote(urlparse(actual_link).path.split("/")[-1])
                        file = self.downloads_folder / filename
                        file.write_bytes((self.session.get(actual_link).content))
                        parsed_post["attachment_type"] = "file"
                        parsed_post["attachment"] = file
                elif attachment_link.startswith("/photo"):
                    # the attachment is an image
                    parsed_post["attachment_type"] = "image"
                    try:
                        image_url = self.FB_BASE_URL + attachment_link
                        image_id = parse_qs(urlparse(image_url).query)["fbid"][0]
                        redirect_url = self.session.get(
                            f"{self.FB_BASE_URL}/photo/view_full_size/?fbid={image_id}"
                        )
                        redirect_soup = BeautifulSoup(redirect_url.content, "lxml")
                        parsed_post["attachment"] = redirect_soup.find("a")["href"]
                    except Exception as e:
                        print(e)
                        parsed_post["attachment"] = attachment_container.find("img")[
                            "src"
                        ]

            parsed_post["parse_complete"] = True
        except Exception as e:
            print(e)

        return parsed_post

    def get_posts(self, look_back):
        latest_posts = self.fetch_new_posts(look_back)
        return [self.parse_post(post["id"], post["time"]) for post in latest_posts]



