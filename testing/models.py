from decimal import Decimal
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

# Physical limits for accepted input. These reject impossible readings; they
# are *not* quality standards (see ``testing.criteria`` for those).
PH_MIN, PH_MAX = Decimal('0'), Decimal('14')
MOISTURE_MIN, MOISTURE_MAX = Decimal('0'), Decimal('100')


class FeedSample(models.Model):
    """A feed or silage sample submitted by a farmer."""

    class FeedType(models.TextChoices):
        SILAGE = 'silage', 'Silage (general)'
        CORN_SILAGE = 'corn_silage', 'Corn silage'
        HAYLAGE = 'haylage', 'Grass / legume silage (haylage)'
        GREEN_FODDER = 'green_fodder', 'Green fodder'
        DRY_FODDER = 'dry_fodder', 'Dry fodder'
        HAY = 'hay', 'Hay'
        CONCENTRATE = 'concentrate', 'Concentrate'
        OTHER = 'other', 'Other'

        @classmethod
        def silage_types(cls):
            """Feed types that are fermented, where a sour smell is expected."""
            return {cls.SILAGE, cls.CORN_SILAGE, cls.HAYLAGE}

    class Smell(models.TextChoices):
        FRESH = 'fresh', 'Fresh'
        SLIGHTLY_SOUR = 'slightly_sour', 'Slightly sour'
        STRONGLY_SOUR = 'strongly_sour', 'Strongly sour'
        MUSTY = 'musty', 'Musty'
        ROTTEN = 'rotten', 'Rotten'
        OTHER = 'other', 'Other'

    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feed_samples',
    )
    sample_name = models.CharField(max_length=100)
    feed_type = models.CharField(max_length=20, choices=FeedType.choices)
    collection_date = models.DateField(default=timezone.localdate)
    ph_value = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(PH_MIN), MaxValueValidator(PH_MAX)],
    )
    moisture = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(MOISTURE_MIN), MaxValueValidator(MOISTURE_MAX)],
    )
    temperature = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(settings.SAMPLE_TEMPERATURE_MIN_C),
            MaxValueValidator(settings.SAMPLE_TEMPERATURE_MAX_C),
        ],
    )
    smell = models.CharField(max_length=100, choices=Smell.choices)
    mold_present = models.BooleanField(default=False)
    observations = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['farmer', '-created_at'], name='sample_farmer_created_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ph_value__gte=PH_MIN, ph_value__lte=PH_MAX),
                name='sample_ph_between_0_and_14',
            ),
            models.CheckConstraint(
                condition=models.Q(moisture__gte=MOISTURE_MIN, moisture__lte=MOISTURE_MAX),
                name='sample_moisture_between_0_and_100',
            ),
        ]

    def __str__(self):
        return f'{self.sample_name} ({self.get_feed_type_display()})'

    @property
    def result(self):
        """Return the sample's assessment, or ``None`` if it has not been assessed."""
        try:
            return self.test_result
        except TestResult.DoesNotExist:
            return None


class TestResult(models.Model):
    """The single most recent quality assessment for a feed sample."""

    # Not a test case: stop test runners such as pytest from collecting it.
    __test__ = False

    class Status(models.TextChoices):
        INCOMPLETE = 'Incomplete', 'Incomplete'
        NEEDS_REVIEW = 'Needs review', 'Needs review'
        BORDERLINE = 'Borderline', 'Borderline'
        WITHIN_CRITERIA = 'Within prototype criteria', 'Within prototype criteria'

    sample = models.OneToOneField(
        FeedSample,
        on_delete=models.CASCADE,
        related_name='test_result',
    )
    quality_score = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='0-100 screening score; empty when the assessment is incomplete.',
    )
    quality_status = models.CharField(max_length=30, choices=Status.choices)
    assessment_explanation = models.TextField(blank=True)
    recommendations = models.TextField()
    findings = models.JSONField(
        default=list,
        blank=True,
        help_text='Per-parameter findings used to build the explanation and score.',
    )
    tested_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-tested_at']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(quality_score__isnull=True)
                    | models.Q(quality_score__gte=0, quality_score__lte=100)
                ),
                name='result_score_between_0_and_100',
            ),
        ]

    def __str__(self):
        return f'{self.sample.sample_name}: {self.quality_status}'

    @property
    def recommendation_list(self):
        return [line for line in self.recommendations.splitlines() if line.strip()]


class ContactMessage(models.Model):
    """A message submitted through the public contact form."""

    name = models.CharField(max_length=100)
    email = models.EmailField()
    message = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_handled = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} <{self.email}> ({self.created_at:%Y-%m-%d})'
