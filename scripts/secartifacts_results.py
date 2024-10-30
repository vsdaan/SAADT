#!/usr/bin/env python3
import argparse
import logging
import sys
from typing import Any

import bs4.formatter
import yaml
from bs4 import BeautifulSoup

from saadt.model import ArtifactBadge, Paper, ACMArtifactBadge
from saadt.scraper import Scraper
from saadt.scraper.acsac import AcsacScraper
from saadt.util import log


def get_scraper(typ: str, edition: str, max_workers: int = 1, max_threads: int = 2) -> Scraper:
    match typ:
        case "acsac":
            return AcsacScraper(edition, max_threads=max_threads)

    raise ValueError(f"conference not supported: {typ}")


def sanitize_badges(paper: Paper) -> None:
    badges = set(paper.badges)
    if ACMArtifactBadge.REUSABLE in badges:
        badges.remove(ACMArtifactBadge.FUNCTIONAL)

    paper.badges = list(badges)


def format_artifact(paper: Paper) -> dict[str, str]:
    sanitize_badges(paper)

    result = {
        "title": str(paper.title),
        "badges": ",".join([badge.name.lower() for badge in paper.badges]),
    }
    if len(paper.artifact_links) > 0:
        result["artifact_url"] = " ".join(paper.artifact_links)
    if paper.pdf_link is not None:
        result["paper_url"] = paper.pdf_link
    elif paper.page_link is not None:
        result["paper_url"] = paper.page_link

    if paper.appendix_link is not None:
        result["appendix_url"] = paper.appendix_link

    return result


def generate_html(badges: list[ArtifactBadge]) -> str:
    html = "<table><thead><tr><th>Title</th>"
    html += "".join([f"<th>{badge.name[0:5].capitalize()}.</th>" for badge in badges])
    html += "<th>Available At</th>"
    html += "</tr></thead><tbody>"
    html += """
    {% for artifact in page.artifacts %}
    <tr>
        <td>
        {% if artifact.paper_url %}
            <a href="{{artifact.paper_url}}" target="_blank">{{artifact.title}}</a>
        {% else %}
            {{ artifact.title }}
        {% endif %}
        </td>
    """

    for badge in badges:
        html += """
        <td width="62px">
            {%% if artifact.badges contains "%s" %%}
                <img src="{{ site.baseurl }}/images/{{ page.%s }}" alt="{{ page.%s }}">
            {%% endif %%}
        </td>
        """ % (badge.name.lower(), f"{badge.name.lower()}_img", f"{badge.name.lower()}_name")  # noqa: UP031

    html += """
    <td>
        {% if artifact.artifact_url %}
            {% assign artifacts = artifact.artifact_url | split: " " %}
            {% for url in artifacts %}  
                <a href="{{url}}" target="_blank">Artifact</a><br>
            {% endfor %}
        {% endif %}
        {% if artifact.appendix_url %}
            <a href="{{artifact.appendix_url}}" target="_blank">Appendix</a><br>
        {% endif %}
    </td>
    """
    html += "</tr>{% endfor %}</tbody></table>"

    soup = BeautifulSoup(html, "html.parser")

    return soup.prettify(
        formatter=bs4.formatter.HTMLFormatter(
            indent=2,
            void_element_close_prefix="",
            empty_attributes_are_booleans=True,
        )
    )


def format_results(papers: list[Paper]) -> str:
    # Find papers with artifacts
    artifact_papers = []
    # For-loop for clarity
    for paper in papers:
        if len(paper.badges) > 0:
            artifact_papers.append(paper)

    # looks nicer on the website :)
    artifact_papers.sort(key=lambda x: str(x.title))

    # Prepare data for output
    data: dict[str, Any] = {
        "title": "Results",
        "order": 20,  # Depends on where the result needs to be in sidebar
    }

    artifacts: list[dict[str, str]] = []
    badge_papers: dict[ArtifactBadge, list[str]] = {}
    for paper in artifact_papers:
        artifacts.append(format_artifact(paper))
        for badge in paper.badges:
            badge_papers.setdefault(badge, []).append(str(paper.title))

    # Sort badges by definition order. Use class to avoid checking for badge type.
    badges = sorted(badge_papers.keys(), key=lambda x: list(x.__class__).index(x))

    # prepare badges metadata
    for badge in badges:
        data[f"{badge.name.lower()}_img"] = f"{type(badge).__name__.lower()}_{badge.name.lower()}.png"
        data[f"{badge.name.lower()}_name"] = badge.value

    data["artifacts"] = artifacts

    result = "---\n"
    result += yaml.safe_dump(data, default_flow_style=False, sort_keys=False, indent=4, width=float("inf"))
    result += "---\n\n"

    result += "**Evaluation Results**:\n\n"
    result += "\n".join([f"* {len(badge_papers[badge])} {badge.value}" for badge in badges])
    result += "\n\n"
    result += generate_html(badges)

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("conference")
    parser.add_argument("edition")
    args = parser.parse_args()

    # Optional: Initialize the logger
    log.get_logger(logging.INFO)

    scraper = get_scraper(args.conference, args.edition)

    # Run scraper
    # Watch the log output for errors!
    papers = scraper.run()
    result = format_results(papers)

    print(result)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt as e:
        logging.info(f'{type(e).__name__}: {"Terminated."}')
        sys.exit(1)
