"""Reference ranges used by the rule-based assessment engine.

Each measured parameter has two bands per feed type:

* ``optimal``    - the range expected for well-made / well-stored feed.
* ``acceptable`` - a wider range that is not ideal but not clearly a problem.
                   It always encloses the optimal band.

Anything outside ``acceptable`` is flagged for review.

Sources and limits
------------------
Silage pH and moisture ranges follow published extension guidance:

* Kung & Shaver, "Interpretation and Use of Silage Fermentation Analysis
  Reports", University of Wisconsin-Madison Extension (corn silage pH 3.7-4.2
  at 30-40 % dry matter).
* Amaral-Phillips, "Fermentation Analysis of Silages", University of Kentucky
  Cooperative Extension (legume/grass silage pH 4.3-5.0 depending on dry matter).

Hay, dry fodder, green fodder, concentrate and temperature bands are
simplified, conservative values for screening purposes and have **not** been
checked against a specific national standard. Before using this tool for real
decisions, review every value below with a qualified animal nutritionist or
your institution's references (for example ICAR / NDDB guidance) and edit this
file accordingly. All values are plain data; no other code needs to change.
"""

from dataclasses import dataclass
from decimal import Decimal

from .models import FeedSample

FeedType = FeedSample.FeedType


@dataclass(frozen=True)
class Band:
    """An inclusive numeric range."""

    low: Decimal
    high: Decimal

    def __contains__(self, value: Decimal) -> bool:
        return self.low <= value <= self.high

    def __str__(self) -> str:
        return f'{self.low.normalize():f}\u2013{self.high.normalize():f}'


@dataclass(frozen=True)
class ParameterCriteria:
    """Optimal and acceptable bands for one measured parameter."""

    optimal: Band
    acceptable: Band

    def __post_init__(self):
        if not (self.acceptable.low <= self.optimal.low and self.optimal.high <= self.acceptable.high):
            raise ValueError('The acceptable band must enclose the optimal band.')


@dataclass(frozen=True)
class FeedProfile:
    """Reference criteria for one feed type."""

    ph: ParameterCriteria
    moisture: ParameterCriteria
    temperature: ParameterCriteria


def _criteria(optimal: tuple, acceptable: tuple) -> ParameterCriteria:
    """Build ``ParameterCriteria`` from ``(low, high)`` pairs of plain numbers."""

    def band(pair):
        return Band(Decimal(str(pair[0])), Decimal(str(pair[1])))

    return ParameterCriteria(optimal=band(optimal), acceptable=band(acceptable))


# Sample temperature is judged against one general band because the form does
# not capture ambient temperature. A reading well above ambient is the real
# warning sign of heating; this simplification can only be a rough screen.
_TEMPERATURE = _criteria(optimal=(5, 30), acceptable=(0, 40))

# Dry, stored feeds share the same simplified pH band.
_DRY_FEED_PH = _criteria(optimal=(5.5, 7.0), acceptable=(5.0, 7.5))


FEED_PROFILES: dict[str, FeedProfile] = {
    # Fermented feeds: a low pH is the sign of a good fermentation.
    FeedType.CORN_SILAGE: FeedProfile(
        ph=_criteria(optimal=(3.7, 4.2), acceptable=(3.5, 4.5)),
        moisture=_criteria(optimal=(60, 70), acceptable=(55, 75)),
        temperature=_TEMPERATURE,
    ),
    FeedType.HAYLAGE: FeedProfile(
        ph=_criteria(optimal=(4.3, 5.0), acceptable=(4.0, 5.3)),
        moisture=_criteria(optimal=(45, 65), acceptable=(40, 70)),
        temperature=_TEMPERATURE,
    ),
    FeedType.SILAGE: FeedProfile(
        ph=_criteria(optimal=(3.7, 4.7), acceptable=(3.5, 5.0)),
        moisture=_criteria(optimal=(55, 70), acceptable=(45, 75)),
        temperature=_TEMPERATURE,
    ),
    # Unfermented feeds.
    FeedType.GREEN_FODDER: FeedProfile(
        ph=_criteria(optimal=(5.5, 7.0), acceptable=(5.0, 7.5)),
        moisture=_criteria(optimal=(70, 85), acceptable=(60, 90)),
        temperature=_TEMPERATURE,
    ),
    FeedType.HAY: FeedProfile(
        ph=_DRY_FEED_PH,
        moisture=_criteria(optimal=(8, 15), acceptable=(5, 18)),
        temperature=_TEMPERATURE,
    ),
    FeedType.DRY_FODDER: FeedProfile(
        ph=_DRY_FEED_PH,
        moisture=_criteria(optimal=(5, 12), acceptable=(0, 15)),
        temperature=_TEMPERATURE,
    ),
    FeedType.CONCENTRATE: FeedProfile(
        ph=_DRY_FEED_PH,
        moisture=_criteria(optimal=(8, 12), acceptable=(5, 14)),
        temperature=_TEMPERATURE,
    ),
    # Fallback for feeds we have no specific guidance for: deliberately wide.
    FeedType.OTHER: FeedProfile(
        ph=_criteria(optimal=(5.5, 7.0), acceptable=(5.0, 7.5)),
        moisture=_criteria(optimal=(10, 70), acceptable=(0, 80)),
        temperature=_TEMPERATURE,
    ),
}


def profile_for(feed_type: str | None) -> FeedProfile:
    """Return the profile for ``feed_type``, falling back to ``other``."""
    return FEED_PROFILES.get(feed_type, FEED_PROFILES[FeedType.OTHER])


# Relative importance of each check. Weights must add up to 100 so a perfect
# sample scores exactly 100.
SCORE_WEIGHTS: dict[str, int] = {
    'ph_value': 25,
    'moisture': 25,
    'temperature': 15,
    'smell': 20,
    'mold_present': 15,
}
if sum(SCORE_WEIGHTS.values()) != 100:
    raise ValueError('SCORE_WEIGHTS must add up to 100.')

# Fraction of a check's weight earned at each level.
BORDERLINE_CREDIT = Decimal('0.5')

# A sample with a failing check cannot look "good" on score alone.
MAX_SCORE_WITH_FLAG = 69
# Visible mold is treated as the most serious observation.
MAX_SCORE_WITH_MOLD = 40
