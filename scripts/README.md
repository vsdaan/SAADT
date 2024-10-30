# Random assortment of scripts

This directory contains a collection of scripts that use the saadt library.
As the library is quite complex, these can be used as examples.

_The saadt library needs to be installed, or add the directory to `$PYTHONPATH`_

## Overview

Many of these scripts where used for developing or generating data and aren't necessarily useful anymore.

| Script                          | Explanation                                                                   |
|---------------------------------|-------------------------------------------------------------------------------|
| secartifacts_results.py         | Generates a secartifacts.github.io results page                               |
| parse_paper_headers.py          | Parses the title of the given papers                                          |
| check_secartifacts_artifacts.py | Compares the papers of given data file to the corresponding secartifacts page |
| scrape_conference.py            | Scrape the conference website for accepted papers and artifacts               |
| download.py                     | Download the PDFs in a scraped conference data file                           |
| scrape_pdfs.py                  | Scrapes pdfs for links.                                                       |
| rank_links.py                   | Script to rank links scraped from a paper. Run scrape_pdfs first.             |
| validate_links.py               | Script to validate links from a scraped paper                                 |

### Scraping a conference workflow

1. `mkdir usenix_23`
2. Scrape the conference: `./scrape_conference.py usenix 23 > usenix_23/data.json`
3. Download the papers: `./download.py usenix_23/data.json usenix_23/`
4. Scrape the PDFs for links: `./scrape_pdfs.py usenix_23/data.json usenix_23/ > usenix_23/links.json`
5. Rank the links: `./rank_links.py usenix_23/links.json usenix_23/ > usenix_23/ranked.json`

> [!WARNING]
> Always redirect the output of a script to a file. The result of a script is
> often multiple megabytes (expect 200.000+ lines) of json.

## Important

### Debugging

- `-v` enables debug logging, but only for the saadt library itself. The reason
  for this is that urllib3 and other libraries often have very verbose logging
  themselves which causes the output to be unreadable.
- `--debug` accepts a file as argument. If provided, all debug logs will be
  written to this file. This can be useful to debug strange issues.

### Using the library

- **ALWAYS** wrap your code in `if __name__ == "__main__":`.
  Many parts of the library use multithreading and multiprocessing.

### Typing

Everything should be fully typed using mypy 1.10. Feel free to ignore it.