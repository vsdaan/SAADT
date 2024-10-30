import urllib3


def safe_parse_url(link: str) -> urllib3.util.Url:
    try:
        url = urllib3.util.parse_url(str(link))
        if not url.scheme:
            url = urllib3.util.Url("https", url.auth, url.host, url.port, url.path, url.query, url.fragment)
    except ValueError:
        url = urllib3.util.Url()

    return url
