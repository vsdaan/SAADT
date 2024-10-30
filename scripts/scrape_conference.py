#!/usr/bin/env python3
import argparse
import logging
import sys

from saadt import model
from saadt.scraper import Scraper
from saadt.scraper.acsac import AcsacScraper
from saadt.scraper.ches import ChesScraper
from saadt.scraper.usenix import UsenixPreScraper, UsenixScraper
from saadt.scraper.woot import WootScraper
from saadt.util import get_proxy
from saadt.util.log import get_logger


def get_scraper(
    typ: str, edition: str, max_workers: int = 2, max_threads: int = 2, proxies: dict[str, str] | None = None
) -> Scraper:
    match typ:
        case "acsac":
            return AcsacScraper(edition, max_threads=max_threads, proxies=proxies)
        case "ches":
            return ChesScraper(edition, max_workers=max_workers, max_threads=max_threads, proxies=proxies)
        case "usenix":
            return UsenixScraper(edition, max_workers=max_workers, max_threads=max_threads, proxies=proxies)
        case "usenix_pre":
            return UsenixPreScraper(edition, max_workers=max_workers, max_threads=max_threads, proxies=proxies)
        case "woot":
            return WootScraper(edition, proxies=proxies)

    raise ValueError(f"conference not supported: {typ}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Conference artifact scraper")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose operation")
    parser.add_argument("-q", "--quiet", action="store_true", default=0, help="Disable all logging")
    parser.add_argument("--debug", metavar="[debug file]", help="path to file for debug logging")
    parser.add_argument("conference", help="Conference type")
    parser.add_argument("edition", help="Edition (year) of the conference")
    args = parser.parse_args()

    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    if args.quiet:
        level = logging.ERROR
    log = get_logger(level, args.debug)

    proxy = get_proxy()
    m = get_scraper(args.conference, args.edition, proxies=proxy)
    try:
        papers = m.run()
    except Exception as exc:
        log.critical("Error scraping papers: %s", exc, exc_info=exc)
        sys.exit(1)

    log.info("Found %d papers", len(papers))

    model.dump_config(args.conference, args.edition, papers)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt as e:
        logging.info(f'{type(e).__name__}: {"Terminated."}')
        sys.exit(1)
