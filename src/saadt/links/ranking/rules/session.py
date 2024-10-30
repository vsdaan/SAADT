import dataclasses
from abc import ABC

import requests
from urllib3.util import Url

from saadt.links.ranking.rules.base import AbstractRule, RuleContext


@dataclasses.dataclass(slots=True)
class SessionRuleContext(RuleContext):
    url: Url
    session: requests.Session


class SessionBaseRule(AbstractRule[SessionRuleContext], ABC):
    pass
