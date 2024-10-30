import dataclasses
import tempfile
import warnings
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any, NamedTuple, override

import requests
import urllib3.util
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from git import GitError
from requests import RequestException
from urllib3.util import Url, parse_url

from . import git
from .util import find_readme


class CrawlerError(Exception):
    pass


@dataclasses.dataclass
class BaseContender:
    """
    The BaseContender class represents a piece of content retrieved from a URL by a BaseCrawler.
    Each contender competes to match the specified paper and serves as a potential match.
    Multiple contenders may be returned by the crawler for a given URL, each representing a different piece of content.
    """

    content: str
    """The actual retrieved content"""

    score: int = 0
    metadata: dict[str, Any] | None = dataclasses.field(default=None)


class LinkContext(NamedTuple):
    url: urllib3.util.Url


class BaseCrawler(ABC):
    context: LinkContext

    def __init__(self, ctx: LinkContext):
        self.context = ctx

    @abstractmethod
    def crawl(self) -> Iterable[BaseContender]:
        pass

    @abstractmethod
    def metadata(self) -> dict[str, str | list[str]] | None:
        pass


class GitCrawler(BaseCrawler):
    max_depth: int = 5
    repo_path: str

    _repo: git.Repo | None = None

    def __init__(self, ctx: LinkContext, work_path: str):
        super().__init__(ctx)
        self.work_path = work_path
        self.repo_path = tempfile.mkdtemp(dir=self.work_path, prefix="git_")

    def clone(self, url: str) -> git.Repo:
        try:
            repo = git.Repo(url, self.repo_path)
        except GitError as ex:
            raise CrawlerError("Error cloning repo") from ex

        return repo

    @override
    def crawl(self) -> Iterable[BaseContender]:
        for file in self.find_readme(self.repo):
            contender = BaseContender(content=self.repo.readfile(file), metadata={"path": file})
            yield contender

    @override
    def metadata(self) -> dict[str, str | list[str]]:
        # TODO: implement this
        # tags
        # Dockerfile or process list of regexes
        return {}

    def find_readme(self, repo: git.Repo) -> Iterable[str]:
        for i, file in enumerate(find_readme(repo.files())):
            if i == self.max_depth:
                break
            yield str(file)

    @property
    def repo(self) -> git.Repo:
        if self._repo is None:
            self._repo = self.clone(self.context.url.url)
        return self._repo

    @repo.setter
    def repo(self, repo: git.Repo) -> None:
        if self._repo is not None:
            raise AttributeError("repo already set")
        self._repo = repo


class GitCrawlerManager:
    cloned_repos: dict[str, str] = {}
    http_client: requests.Session

    def __init__(self, session: requests.Session):
        self.session = session

    def create(self, ctx: LinkContext, work_path: str) -> GitCrawler | None:
        crawler = GitCrawler(ctx, work_path)

        clone_url = self.get_clone_url(ctx.url)
        if clone_url is None:
            return None

        clone_url_str = clone_url.url
        if clone_url_str in self.cloned_repos:
            crawler.repo = git.Repo(clone_url_str, self.cloned_repos[clone_url_str], exists=True)

        self.cloned_repos[clone_url_str] = crawler.repo_path
        return crawler

    def get_clone_url(self, url: Url) -> Url | None:
        if url.path is not None and url.path.endswith(".git"):
            return url

        r = self.session.head(url.url)
        if r.headers is None:
            return None

        if "Location" in r.headers:
            url = parse_url(r.headers["Location"])

        if url.host is None or url.path is None:
            return None

        if "github.com" in url.host:
            return self._parse_safe_url(url)

        if "gitlab.com" in url.host or "x-gitlab-meta" in r.headers:
            return self._parse_safe_url(url)

        if "bitbucket.org" in url.host:
            return self._parse_safe_url(url)

        return None

        # try adding .git  # return Url(scheme=url.scheme, host=url.host, path=f"{url.path.rstrip("/")}.git")

    def _parse_safe_url(self, url: Url) -> Url | None:
        assert url.host is not None
        assert url.path is not None

        path = url.path.strip("/").split("/", 2)
        if len(path) < 2:
            return None
        return Url(scheme=url.scheme, host=url.host, path=f"/{'/'.join(path[0:2])}.git")


class WebpageCrawler(BaseCrawler):
    session: requests.Session

    def __init__(self, ctx: LinkContext, session: requests.Session):
        super().__init__(ctx)
        self.session = session

        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

    @override
    def crawl(self) -> Iterable[BaseContender]:
        try:
            resp = self.session.get(self.context.url.url, stream=True)
            resp.raise_for_status()
        except RequestException as exc:
            raise CrawlerError(f'Error downloading webpage for url="{self.context.url.url}"') from exc

        ct = resp.headers.get("Content-Type")
        if ct is None or "text/" not in ct:
            resp.close()
            raise CrawlerError(f'Unsupported Content-Type="{ct}".', ct)

        soup = BeautifulSoup(resp.content, "lxml")
        resp.close()

        contender = BaseContender(content=soup.get_text())
        yield contender

    @override
    def metadata(self) -> dict[str, str | list[str]] | None:
        pass


class CrawlerFactory:
    session: requests.Session
    work_path: str
    git_crawler_manager: GitCrawlerManager

    def __init__(self, session: requests.Session, work_path: str):
        self.session = session
        self.work_path = work_path
        self.git_crawler_manager = GitCrawlerManager(session)

    def create(self, ctx: LinkContext) -> BaseCrawler | None:
        crawler = self.git_crawler_manager.create(ctx, self.work_path)
        if crawler is not None:
            return crawler

        return WebpageCrawler(ctx, self.session)
