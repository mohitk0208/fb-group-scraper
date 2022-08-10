# Facebook Group Scraper

`main.py` is a python script to scrape and parse latest posts from a facebook group, it can also send updates to a telegram chat or channel.

## Requirements

- Facebook cookies: obviously
- Pipenv: manage python environment
- Telegram bot: to send messages on telegram
- Direnv(optional)

## Usage

Install dependencies

`pipenv install`

get cookies from facebook and put the in `.env` file (refer to `.env.example` for required values)

Run the scraper

`pipenv run python main.py`

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).