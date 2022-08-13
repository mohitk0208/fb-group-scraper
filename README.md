# Facebook Group Scraper

`main.py` is a python script to scrape and parse latest posts from a facebook group, it can also send updates to a telegram chat or channel.

## Requirements

- Facebook cookies: for obvious reasons
- Pipenv: manage python environment
- Telegram bot: send messages on telegram
- Direnv(optional): automatically load environment

## Usage

- Install dependencies

    ```shell
    pipenv install
    ```

- Get cookies from facebook and put them in `.env` file (refer to `.env.example` for required values)

- Run the scraper

    ```shell
    pipenv run python main.py
    ```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).