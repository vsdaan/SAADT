#!/usr/bin/env python3
import argparse
import dataclasses
import json
import logging
import sys

import requests
from _model import ComparedPaper, parse_links_file, parse_ranked_file
from urllib3.util import Url, parse_url

from saadt.links.parsing import ParsedPaper
from saadt.links.ranking import RankedLink
from saadt.model import parse_config
from saadt.model.paper import Paper
from saadt.scraper.util import TitleMatcher
from saadt.util import secartifacts
from saadt.util.log import get_logger
from saadt.util.secartifacts import SecartifactsArtifact


def _try_parse_url(link: str | None) -> Url | None:
    try:
        if not link:
            return None
        url = parse_url(link)
        if url.scheme is None:
            url = Url("http", url.auth, url.host, url.port, url.path, url.query, url.fragment)
        return url
    except ValueError:
        return None


def may_match(url: Url) -> bool:
    if url.host == "github.com":
        if url.path is None:
            return False
        if len(url.path.strip("/").split("/")) < 2:
            return False
        return True

    return True


def normalize(url: Url) -> Url:
    if url.host == "github.com":
        if url.path is None:
            return url
        path_parts = url.path.strip("/").split("/")
        if len(path_parts) >= 4:
            if path_parts[2] == "releases" and path_parts[3] == "tag":
                del path_parts[3]
                path_parts[2] = "tree"
        if len(path_parts) > 2:
            if path_parts[2] in ["commit"]:
                path_parts[2] = "tree"

        url = Url(
            "https",
            url.auth,
            url.host,
            url.port,
            "/".join(path_parts).removesuffix(".git").lower(),
            url.query,
            url.fragment,
        )
    return url


def compare_paths(a: str, b: str) -> bool:
    sa = a.strip("/").split("/")
    sb = b.strip("/").split("/")

    if len(sb) > len(sa):
        return False

    for i in range(len(sb)):
        if sa[i] != sb[i]:
            return False

    return True


def compare(
    log: logging.Logger,
    papers: list[ParsedPaper],
    links: dict[str, list[RankedLink]],
    groundtruth: list[SecartifactsArtifact],
) -> list[ComparedPaper]:
    m = TitleMatcher(groundtruth, key=lambda x: str(x.title))

    session = requests.Session()
    result = []

    for paper in papers:
        if paper.id() not in links:
            continue

        artifact = m.unsafe_match(str(paper.title))
        if artifact is None:
            log.error("Failed to find groundtruth for paper: %s", paper.title)
            continue

        if artifact.artifact_urls is None:
            log.warning("No artifact urls in groundtruth %s", artifact.title)
            result.append(ComparedPaper(str(paper.title), None, tuple(links[paper.id()])))
            continue

        cps = []
        for artifact_url_str in artifact.artifact_urls:
            cp = ComparedPaper(str(paper.title), artifact_url_str, tuple(links[paper.id()]))
            cps.append(cp)

            artifact_url = _try_parse_url(artifact_url_str.lower())
            artifact_url = normalize(artifact_url)
            if artifact_url is None:
                log.warning("Failed to parse artifact url: %s, paper: %s", artifact_url_str, artifact.title)
                continue

            best_match_length = -1
            for i, link in enumerate(cp.links):
                url = _try_parse_url(link.link.lower())
                if url is None:
                    continue
                url = normalize(url)

                if "doi.org" in url.host and artifact_url.host != url.host:
                    r = session.head(url.url)
                    if "Location" in r.headers:
                        url = _try_parse_url(r.headers["Location"])
                if artifact_url.host != url.host:
                    continue

                if not may_match(url):
                    continue

                if cp.exact_match_index == -1 and artifact_url.path == url.path:
                    cp.exact_match_index = i

                artifact_path = artifact_url.path or ""
                url_path = url.path or ""
                if compare_paths(artifact_path, url_path):
                    if cp.closest_partial_match_index == -1:
                        cp.closest_partial_match_index = i
                    if len(url_path) > best_match_length:
                        best_match_length = len(url_path)
                        cp.best_match_index = i

        cps_exact = sorted(filter(lambda c: c.exact_match_index != -1, cps), key=lambda c: c.exact_match_index)
        if len(cps_exact) > 0:
            result.append(cps_exact[0])
            continue

        cps_best = sorted(filter(lambda c: c.best_match_index != -1, cps), key=lambda c: c.best_match_index)
        if len(cps_best) > 0:
            result.append(cps_best[0])
            continue

        result.append(cps[0])

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare ranked links to secartifacts")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose operation")
    parser.add_argument("-q", "--quiet", action="store_true", default=0, help="Disable all logging")
    parser.add_argument("--debug", metavar="[debug file]", help="path to file for debug logging")
    parser.add_argument("config_file_path", metavar="[config file]", help="config file location")
    parser.add_argument("links_file_path", metavar="[list.json file]", help="path to paper links file")
    parser.add_argument("ranked_links_path", metavar="[ranked.json file]", help="path to ranked links file")
    args = parser.parse_args()

    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    if args.quiet:
        level = logging.ERROR
    log = get_logger(level, args.debug)

    cfg = parse_config(args.config_file_path, Paper)
    papers = parse_links_file(args.links_file_path)

    log.info(f"Processing {len(papers)} papers of {cfg['conference']} 20{cfg['edition']}")

    if cfg["conference"] == "acsac":
        ground_truth = [
            SecartifactsArtifact(str(p.title), p.artifact_links, p.appendix_link, p.pdf_link, p.badges)
            for p in papers
            if len(p.artifact_links) > 0
        ]
    else:
        ground_truth = secartifacts.SecartifactsScraper(cfg["conference"], cfg["edition"]).artifacts
    ranked = parse_ranked_file(args.ranked_links_path)

    result = compare(log, papers, ranked, ground_truth)
    d = []
    for item in result:
        d.append(dataclasses.asdict(item))
    json.dump(d, sys.stdout, indent=4)

    log.info("Finished")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt as e:
        logging.info(f'{type(e).__name__}: {"Terminated."}')
        sys.exit(1)
