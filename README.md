# Semi-Automatic Artifact Discovery Tool

SAADT is a semi-automatic tool designed to assist researchers in artifact research by automating the discovery,
retrieval, and analysis of research artifacts across conferences. It features advanced web scraping and PDF parsing
to extract links and metadata and a rule-based system for accurate artifact detection and classification.

SAADT was developed for my master's thesis:
_Semi-Automatic Discovery of Paper Artifacts_. The thesis itself can be obtained
from the KU Leuven library or by contacting me.

## Getting started

Install the SAADT library as follows (it's not on pypi):
```bash
# Install from github
pip install saadt @ git+https://github.com/principis/SAADT.git

# If you need everything:
pip install saadt[all] @ git+https://github.com/principis/SAADT.git

# from a different path:
pip install /path/to/src[all]
```

The subpackages often don't import their modules for performance reasons.
Be explicit on what you need:

```python3
from saadt.scraper.acsac import AcsacScraper

s = AcsacScraper("23")
```

Don't know where to start? Look at the [scripts](scripts) directory.

Many things use [multiprocessing](https://docs.python.org/3/library/multiprocessing.html).
Make sure to wrap your code as follows:
```python3
def my_code():
  ...

if __name__ == '__main__':
  my_code()
```

### System dependencies:

_Python dependencies will be installed by pip._

- python >= 3.12
- poppler-glib (for parsing PDFs)
- PyGobject (yes, install it from your distribution)
- libxml2

Fedora: `sudo dnf install python3-pip python3-gobject poppler-glib`

#### If you don't have PyGobject:
Install it from your distribution. If you don't want to, here are the
dependencies. You will need the headers!
- gcc
- python >= 3.12
- pkg-config
- cairo
- cairo-gobject
- gobject-introspection

Fedora: 
`sudo dnf install gcc python3-devel cairo-gobject-devel gobject-introspection-devel`

Other distros: [start here](https://gnome.pages.gitlab.gnome.org/pygobject/getting_started.html).

_Windows: I'm sorry. Good luck._

## Citation
```
@masterthesis{bols2024saadt,
    title     = {Semi-Automatic Discovery of Paper Artifacts},
    author    = {Bols, Arthur and Piessens, Frank and Van Bulck, Jo and Bognár, Márton and KU Leuven. Faculteit Ingenieurswetenschappen. Opleiding Master in de ingenieurswetenschappen. Computerwetenschappen (Leuven) degree granting institution},
    year      = 2024,
    publisher = {KU Leuven. Faculteit Ingenieurswetenschappen}
}
```

## License
This project is licensed under the LGPL-3.0-or-later license. See the [license](LICENSE.txt) file for details.