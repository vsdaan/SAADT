import os


def get_proxy() -> dict[str, str] | None:
    proxy_str = os.environ.get("SCRAPER_PROXY")
    if proxy_str is None:
        return None

    return {
        "http": proxy_str,
        "https": proxy_str,
    }
