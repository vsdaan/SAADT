import sys
import typing
from enum import Enum


class ArtifactBadge(Enum):
    @classmethod
    @typing.no_type_check
    def from_string(cls, s: str) -> "ArtifactBadge":
        k, v = s.split(".")
        return getattr(getattr(sys.modules[__name__], k), v)


class ACMArtifactBadge(ArtifactBadge):
    FUNCTIONAL = "Artifacts Functional"
    """
    Artifacts Evaluated - Functional:

    The artifacts associated with the research are found to be documented, consistent, complete, exercisable, and
    include appropriate evidence of verification and validation.
    """
    REUSABLE = "Artifacts Reusable"
    """
    Artifacts Evaluated - Reusable

    The artifacts associated with the paper are of a quality that significantly exceeds minimal functionality. That is,
    they have all the qualities of the Artifacts Evaluated – Functional level, but, in addition, they are very carefully
    documented and well-structured to the extent that reuse and repurposing is facilitated. In particular, norms and
    standards of the research community for artifacts of this type are strictly adhered to.
    """
    REPRODUCED = "Results Reproduced"
    """
    Results Reproduced:

    The main results of the paper have been obtained in a subsequent study by a person or team other than the authors,
    using, in part, artifacts provided by the author.
    """

    @staticmethod
    def parse_string(s: str) -> "ACMArtifactBadge":
        s = s.lower()
        if "functional" in s:
            return ACMArtifactBadge.FUNCTIONAL
        if "reusable" in s:
            return ACMArtifactBadge.REUSABLE
        if "reproduced" in s:
            return ACMArtifactBadge.REPRODUCED

        raise ValueError


class CHESArtifactBadge(ArtifactBadge):
    FUNCTIONAL = "Functional"
    REPRODUCED = "Reproduced"
    AVAILABLE = "Available"


class UsenixArtifactBadge(ArtifactBadge):
    PASSED = "Evaluation Passed"
    """
    Evaluation Passed:
    (This badge was awarded before 2022)

    Ultimately, we expect artifacts to be:

    - consistent with the paper
    - as complete as possible
    - documented well
    - easy to reuse, facilitating further research
    """
    AVAILABLE = "Available"
    """
    Artifacts Available:

    To earn this badge, the AEC must judge that the artifacts associated with the paper have been made available
    for retrieval, permanently and publicly. The archived copy of the artifacts must be accessible via a stable
    reference or DOI.
    """
    FUNCTIONAL = "Functional"
    """
    Artifacts Functional:

    To earn this badge, the AEC must judge that the artifacts conform to the expectations set by the paper in terms of
    functionality, usability, and relevance. In short, do the artifacts work and are they useful for producing outcomes
    associated with the paper? The AEC will consider three aspects of the artifacts in particular:

    - Documentation: are the artifacts sufficiently documented to enable them to be exercised by readers of the paper?
    - Completeness: do the submitted artifacts include all of the key components described in the paper?
    - Exercisability: do the submitted artifacts include the scripts and data needed to run the experiments described in
     the paper, and can the software be successfully executed?
    """
    REPRODUCED = "Reproduced"
    """
    Results Reproduced:

    To earn this badge, the AEC must judge that they can use the submitted artifacts to obtain
    the main results presented in the paper. In short, is it possible for the AEC to independently repeat the
    experiments and obtain results that support the main claims made by the paper? The goal of this effort is not to
    reproduce the results exactly, but instead to generate results independently within an allowed tolerance such that
    the main claims of the paper are validated.
    """


class WOOTArtifactBadge(ArtifactBadge):
    EVALUATED = "Evaluated"
    ORO = "ORO"
    """
    Open Research Objects (ORO):
    this badge indicates that the artifact is permanently archived in a public repository that assigns
    a global identifier and guarantees persistence, and is made available via standard open licenses
    that maximize artifact availability.
    """
    ROR = "ROR"
    """
    Research Objects Reviewed (ROR):
    this badge indicates that all relevant artifacts used in the research (including data and code) were reviewed
    and conformed to the expectations set by the paper.
    """
