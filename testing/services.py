"""Business operations that combine the assessment engine with persistence."""

from .assessment import assess_sample
from .models import FeedSample, TestResult


def assess_and_store(sample: FeedSample) -> TestResult:
    """Assess ``sample`` and create or update its single stored result."""
    assessment = assess_sample(sample)
    result, _created = TestResult.objects.update_or_create(
        sample=sample,
        defaults=assessment.as_model_fields(),
    )
    return result
