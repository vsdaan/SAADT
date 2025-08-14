import logging
import re
from typing import Any, Unpack, override
from urllib.parse import urljoin

import bs4
import requests
from bs4 import BeautifulSoup
from unidecode import unidecode

from saadt.model import Paper, PaperTitle
from saadt.scraper import ScraperWorker, ThreadedScraper
from saadt.util import mputils
from saadt.util.mputils import WorkerParams

NDSS_BASE_URL = "https://www.ndss-symposium.org/ndss20{year}/accepted-papers/"

log = logging.getLogger(__name__)


class NDSSScraperWorker(ScraperWorker[tuple[PaperTitle, str]]):
    def __init__(
        self,
        edition: str,
        **kwargs: Unpack[WorkerParams[tuple[PaperTitle, str], Paper]],
    ):
        super().__init__(edition, **kwargs)

    def _process_node(self, node: tuple[PaperTitle, str]) -> Paper:
        _, link = node
        self.logger.debug('Processing paper url="%s"', link)
        title, pdf_link = self._parse_paper_page(link)

        paper = Paper(title, link, pdf_link, None, [])
        return paper

    def _parse_paper_page(self, link: str) -> tuple[PaperTitle, str]:
        """Parse the individual paper page to find the title and PDF link."""
        try:
            r = self.session.get(link)
            r.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f'Error fetching paper page="{link}"') from exc

        soup = BeautifulSoup(r.content, "lxml")
        
        # Find the title from h1 with class "entry-title"
        title_element = soup.find("h1", class_="entry-title")
        if not title_element:
            raise Exception(f'Failed to find title for paper page="{link}"')
        
        title_text = title_element.get_text(strip=True)
        if not title_text:
            raise Exception(f'Empty title for paper page="{link}"')
        
        # Clean up the title
        title = PaperTitle(unidecode(title_text.strip()))
        
        # Find PDF link that contains 'wp-content/uploads' and ends with '.pdf'
        pdf_links = soup.find_all("a", href=re.compile(r"wp-content/uploads.*\.pdf$"))
        
        if not pdf_links:
            raise Exception(f'Failed to find PDF for paper page="{link}"')
        
        # Get the first PDF link found
        pdf_link = pdf_links[0].get("href")
        
        # Make sure it's an absolute URL
        if pdf_link and not pdf_link.startswith("http"):
            pdf_link = urljoin(link, pdf_link)
        
        return title, pdf_link


class NDSSScraper(ThreadedScraper[tuple[PaperTitle, str]]):
    def __init__(
        self,
        edition: str,
        max_workers: int = 2,
        max_threads: int = 10,
        proxies: dict[str, str] | None = None,
    ):
        super().__init__(edition, max_workers, max_threads, proxies)

    @override
    def _get_papers(self) -> list[tuple[PaperTitle, str]]:
        log.info("Fetching NDSS papers for edition %s", self.edition)

        try:
            r = self.session.get(NDSS_BASE_URL.format(year=self.edition))
            r.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError("Error fetching NDSS website") from exc

        log.debug("Parsing accepted papers page")
        soup = BeautifulSoup(r.content, "lxml")
        
        # Find all divs with class "rel-paper-in"
        paper_divs = soup.find_all("div", class_="rel-paper-in")
        
        result = []
        for paper_div in paper_divs:
            # Find the link (a tag) within the div
            link_tag = paper_div.find("a")
            if not link_tag:
                continue
                
            href = link_tag.get("href")
            if not href:
                continue
            
            # Make sure it's an absolute URL
            if not href.startswith("http"):
                href = urljoin(NDSS_BASE_URL.format(year=self.edition), href)
            
            # Use a placeholder title since we'll get the real title from the paper page
            placeholder_title = PaperTitle(f"Paper_{len(result) + 1}")
            result.append((placeholder_title, str(href)))

        log.debug("Found %d papers", len(result))
        return result

    @override
    def _get_worker_args(self, i: int) -> tuple[str]:
        return (self.edition,)

    @classmethod
    @override
    def _worker(
        cls,
        *args: str,
        **kwargs: Unpack[mputils.WorkerParams[tuple[PaperTitle, str], Paper]],
    ) -> NDSSScraperWorker:
        return NDSSScraperWorker(*args, **kwargs)
