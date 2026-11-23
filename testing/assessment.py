"""Rule-based feed and silage screening for the NutriFarm AI prototype.

How it works
------------
Five checks are made on every sample: pH, moisture, temperature, smell and
visible mold. Each check yields a :class:`Finding` with one of four levels:

========== ===============================================================
Level      Meaning
========== ===============================================================
optimal    Within the optimal band for the feed type (full credit).
borderline Acceptable but not ideal (half credit).
flagged    Outside the acceptable band, or mold / an off smell (no credit).
missing    The input is absent or unusable (no score can be produced).
========== ===============================================================

The overall category is derived from the findings, and a 0-100 score is the
weighted sum of the credit earned (weights are in ``criteria.SCORE_WEIGHTS``).

This is **not** a trained machine-learning model and has not been validated
against laboratory results. It must not be used to certify that feed is safe.
"""

from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum

from .criteria import (
    BORDERLINE_CREDIT,
    MAX_SCORE_WITH_FLAG,
    MAX_SCORE_WITH_MOLD,
    SCORE_WEIGHTS,
    ParameterCriteria,
    profile_for,
)
from .models import FeedSample, TestResult

Smell = FeedSample.Smell
Status = TestResult.Status

DISCLAIMER = (
    'This is an illustrative, rule-based screening that has not been scientifically '
    'validated and does not certify feed quality or safety. Rely on laboratory testing '
    'and qualified agricultural advice for real decisions.'
)


class Level(StrEnum):
    OPTIMAL = 'optimal'
    BORDERLINE = 'borderline'
    FLAGGED = 'flagged'
    MISSING = 'missing'


_CREDIT = {
    Level.OPTIMAL: Decimal('1'),
    Level.BORDERLINE: BORDERLINE_CREDIT,
    Level.FLAGGED: Decimal('0'),
    Level.MISSING: Decimal('0'),
}


@dataclass(frozen=True)
class Finding:
    """The outcome of a single check."""

    parameter: str
    label: str
    level: Level
    message: str
    recommendation: str
    max_points: int
    points: float

    def to_dict(self) -> dict:
        return {**asdict(self), 'level': self.level.value}


@dataclass(frozen=True)
class Assessment:
    """The complete outcome of assessing one sample."""

    status: str
    score: int | None
    findings: tuple[Finding, ...]

    @property
    def explanation(self) -> str:
        """Human-readable summary, most serious issues first."""
        missing = [f.label for f in self.findings if f.level is Level.MISSING]
        parts = []
        if missing:
            parts.append(
                'The assessment is incomplete because these inputs are missing or unusable: '
                + ', '.join(missing)
                + '.'
            )
        for level in (Level.FLAGGED, Level.BORDERLINE, Level.OPTIMAL):
            parts.extend(f.message for f in self.findings if f.level is level)
        parts.append(DISCLAIMER)
        return ' '.join(parts)

    @property
    def recommendations(self) -> list[str]:
        recommendations = [f.recommendation for f in self.findings if f.recommendation]
        if not recommendations:
            recommendations.append(
                'No parameter-specific concerns were raised by these checks. '
                'This is not a safety determination; consult appropriate agricultural guidance.'
            )
        return recommendations

    def as_model_fields(self) -> dict:
        """Return values ready to store on a :class:`TestResult`."""
        return {
            'quality_status': self.status,
            'quality_score': self.score,
            'assessment_explanation': self.explanation,
            'recommendations': '\n'.join(self.recommendations),
            'findings': [finding.to_dict() for finding in self.findings],
        }


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _to_decimal(value) -> Decimal | None:
    """Return a finite ``Decimal`` for numeric input, or ``None`` when unusable."""
    if value is None or isinstance(value, bool) or value == '':
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _finding(parameter: str, label: str, level: Level, message: str, recommendation: str = ''):
    weight = SCORE_WEIGHTS[parameter]
    return Finding(
        parameter=parameter,
        label=label,
        level=level,
        message=message,
        recommendation=recommendation,
        max_points=weight,
        points=float(weight * _CREDIT[level]),
    )


def _missing(parameter: str, label: str, what: str) -> Finding:
    return _finding(
        parameter,
        label,
        Level.MISSING,
        f'{label} was not recorded or is not a valid value.',
        f'Record {what} before interpreting this sample.',
    )


# Direction-specific advice for out-of-range numeric readings.
_NUMERIC_ADVICE = {
    ('ph_value', 'high'): (
        'A higher-than-expected pH can indicate restricted or poor fermentation in silage. '
        'Confirm the reading and consider a laboratory fermentation analysis.'
    ),
    ('ph_value', 'low'): (
        'A lower-than-expected pH is unusual. Check that the pH meter is calibrated and '
        'repeat the measurement.'
    ),
    ('moisture', 'high'): (
        'Excess moisture raises the risk of poor fermentation (silage) or mold and heating '
        '(hay and dry feeds). Recheck the moisture and review storage.'
    ),
    ('moisture', 'low'): (
        'Very low moisture can reduce packing and fermentation quality in silage. '
        'Recheck the moisture with an appropriate method.'
    ),
    ('temperature', 'high'): (
        'A warm sample can indicate microbial heating or air exposure. Compare it with the '
        'ambient temperature and check how well the feed is sealed and stored.'
    ),
    ('temperature', 'low'): (
        'Verify the temperature reading and the conditions in which the sample was measured.'
    ),
}


def _check_numeric(
    parameter: str,
    label: str,
    unit: str,
    criteria: ParameterCriteria,
    raw_value,
    feed_name: str,
) -> Finding:
    value = _to_decimal(raw_value)
    if value is None:
        return _missing(parameter, label, f'a valid {label.lower()}')

    reading = f'{label} {value.normalize():f}{unit}'
    if value in criteria.optimal:
        return _finding(
            parameter,
            label,
            Level.OPTIMAL,
            f'{reading} is within the optimal range for {feed_name} ({criteria.optimal}{unit}).',
        )
    if value in criteria.acceptable:
        return _finding(
            parameter,
            label,
            Level.BORDERLINE,
            f'{reading} is acceptable but outside the optimal range for {feed_name} '
            f'({criteria.optimal}{unit}).',
            _NUMERIC_ADVICE[(parameter, 'high' if value > criteria.optimal.high else 'low')],
        )
    return _finding(
        parameter,
        label,
        Level.FLAGGED,
        f'{reading} is outside the acceptable range for {feed_name} ({criteria.acceptable}{unit}).',
        _NUMERIC_ADVICE[(parameter, 'high' if value > criteria.acceptable.high else 'low')],
    )


def _check_smell(raw_smell, is_silage: bool) -> Finding:
    parameter, label = 'smell', 'Smell condition'
    smell = raw_smell.strip().lower() if isinstance(raw_smell, str) else ''
    if not smell:
        return _missing(parameter, label, 'the observed smell condition')

    if smell == Smell.FRESH:
        return _finding(parameter, label, Level.OPTIMAL, 'The smell was recorded as fresh.')
    if smell == Smell.SLIGHTLY_SOUR:
        if is_silage:
            return _finding(
                parameter,
                label,
                Level.OPTIMAL,
                'A slightly sour smell is expected for well-fermented silage.',
            )
        return _finding(
            parameter,
            label,
            Level.BORDERLINE,
            'A slightly sour smell is not expected in unfermented feed.',
            'Check whether the feed has started to ferment or heat in storage.',
        )
    if smell in {Smell.STRONGLY_SOUR, Smell.MUSTY, Smell.ROTTEN}:
        display = Smell(smell).label.lower()
        return _finding(
            parameter,
            label,
            Level.FLAGGED,
            f'The smell was recorded as {display}, which is configured for review.',
            'Have the unusual smell investigated by a qualified agricultural advisor.',
        )
    if smell == Smell.OTHER:
        return _finding(
            parameter,
            label,
            Level.BORDERLINE,
            'The smell was recorded as "other", so it could not be interpreted.',
            'Describe the smell in the observations field or ask an advisor to assess it.',
        )
    return _finding(
        parameter,
        label,
        Level.BORDERLINE,
        'The recorded smell is not one of the recognised conditions.',
        'Review the smell observation and use a recognised condition or an expert assessment.',
    )


def _check_mold(mold_present) -> Finding:
    parameter, label = 'mold_present', 'Visible mold'
    if mold_present is None:
        return _missing(parameter, label, 'whether visible mold was observed')
    if mold_present:
        return _finding(
            parameter,
            label,
            Level.FLAGGED,
            'Visible mold was recorded.',
            'Visible mold was reported; consult a qualified feed or veterinary professional '
            'before feeding rather than relying on this screening.',
        )
    return _finding(parameter, label, Level.OPTIMAL, 'No visible mold was recorded.')


def _score(findings: tuple[Finding, ...]) -> int:
    total = sum(Decimal(str(f.points)) for f in findings)
    score = int(total.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    levels = {f.parameter: f.level for f in findings}
    if levels['mold_present'] is Level.FLAGGED:
        score = min(score, MAX_SCORE_WITH_MOLD)
    if any(level is Level.FLAGGED for level in levels.values()):
        score = min(score, MAX_SCORE_WITH_FLAG)
    return score


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def assess_sample(sample) -> Assessment:
    """Assess a sample (any object with the ``FeedSample`` measurement attributes)."""
    feed_type = getattr(sample, 'feed_type', None)
    profile = profile_for(feed_type)
    is_silage = feed_type in FeedSample.FeedType.silage_types()
    try:
        feed_name = FeedSample.FeedType(feed_type).label.lower()
    except ValueError:
        feed_name = 'this feed type'

    findings = (
        _check_numeric('ph_value', 'pH', '', profile.ph, getattr(sample, 'ph_value', None), feed_name),
        _check_numeric(
            'moisture',
            'Moisture',
            '%',
            profile.moisture,
            getattr(sample, 'moisture', None),
            feed_name,
        ),
        _check_numeric(
            'temperature',
            'Temperature',
            '\u00b0C',
            profile.temperature,
            getattr(sample, 'temperature', None),
            feed_name,
        ),
        _check_smell(getattr(sample, 'smell', None), is_silage),
        _check_mold(getattr(sample, 'mold_present', None)),
    )

    levels = {f.level for f in findings}
    if Level.MISSING in levels:
        return Assessment(Status.INCOMPLETE, None, findings)

    score = _score(findings)
    if Level.FLAGGED in levels:
        status = Status.NEEDS_REVIEW
    elif Level.BORDERLINE in levels:
        status = Status.BORDERLINE
    else:
        status = Status.WITHIN_CRITERIA
    return Assessment(status, score, findings)
