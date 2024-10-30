#!/usr/bin/env python3
import argparse
import json
import logging
import os
import pathlib
import sys
from typing import Any

from saadt.links.parsing import LinkParser, ParsedPaper
from saadt.model import Paper, parse_config
from saadt.util.log import get_logger


def process_papers(paper_dir: str, papers: list[Paper], appendix: bool = False) -> list[ParsedPaper]:
    dispatch = []
    for paper in papers:
        file_name = f"{paper.id()}"
        if appendix and paper.appendix_link is None:
            continue

        if appendix:
            file_name += "_appendix"
        path = pathlib.Path(os.path.join(os.path.abspath(paper_dir), f"{file_name}.pdf"))
        dispatch.append((path, paper))

    manager = LinkParser(dispatch)
    result = manager.run()

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="""Conference paper link scraper
        Find all links for the papers from the given config file."""
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose operation")
    parser.add_argument("-q", "--quiet", action="store_true", default=0, help="Disable all logging")
    parser.add_argument("--debug", metavar="[debug file]", help="path to file for debug logging")
    parser.add_argument("--appendix", action="store_true", default=False, help="process appendices")
    parser.add_argument("config_file_path", metavar="[config file]", help="config file location")
    parser.add_argument("paper_dir", help="directory containing the pdfs to process")
    args = parser.parse_args()

    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    if args.quiet:
        level = logging.ERROR
    log = get_logger(level, args.debug)

    cfg = parse_config(args.config_file_path)

    log.info(f"Processing {len(cfg['papers'])} papers of {cfg['conference']} 20{cfg['edition']}")
    result = process_papers(args.paper_dir, cfg["papers"], args.appendix)

    d: list[dict[str, Any]] = []
    for paper in result:
        d.append(paper.to_dict())
    json.dump(d, sys.stdout, indent=4)

    log.info("Finished")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt as e:
        logging.info(f'{type(e).__name__}: {"Terminated."}')
        sys.exit(1)
