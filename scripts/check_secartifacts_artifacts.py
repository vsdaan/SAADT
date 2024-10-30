#!/usr/bin/env python3
import argparse
import logging

from saadt.model import parse_config
from saadt.scraper.util import TitleMatcher
from saadt.util import secartifacts
from saadt.util.log import get_logger


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", help="path to data.json")
    args = parser.parse_args()

    log = get_logger(logging.INFO)

    cfg = parse_config(args.data)
    conference = cfg["conference"]
    edition = cfg["edition"]
    papers = cfg["papers"]

    matcher = TitleMatcher(papers, key=lambda x: str(x.title))
    artifacts = secartifacts.SecartifactsScraper(conference, edition).artifacts

    found_artifacts = [paper for paper in papers if len(paper.badges) != 0]

    if len(found_artifacts) != len(artifacts):
        log.error("found artifacts does not match secartifacts: %s != %s", len(found_artifacts), len(artifacts))

    for artifact in artifacts:
        match = matcher.unsafe_match(artifact.title)
        if match is None:
            log.error(f"No match for artifact {artifact.title}")
            continue

        if str(match.title) != artifact.title:
            log.warning(f"Paper '{artifact.title}' does not match '{str(match.title)}'")


if __name__ == "__main__":
    main()
