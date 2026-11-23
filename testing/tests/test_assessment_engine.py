from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from testing.assessment import Level, assess_sample
from testing.criteria import (
    FEED_PROFILES,
    SCORE_WEIGHTS,
    Band,
    ParameterCriteria,
    profile_for,
)
from testing.models import FeedSample, TestResult
from testing.services import assess_and_store

from .factories import make_farmer, make_sample

FeedType = FeedSample.FeedType
Status = TestResult.Status


def sample_values(**overrides):
    """A plain object shaped like a well-fermented corn silage sample."""
    values = {
        'feed_type': FeedType.CORN_SILAGE,
        'ph_value': Decimal('4.00'),
        'moisture': Decimal('65.00'),
        'temperature': Decimal('20.00'),
        'smell': 'slightly_sour',
        'mold_present': False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def levels(assessment):
    return {finding.parameter: finding.level for finding in assessment.findings}


class CriteriaTests(SimpleTestCase):
    def test_every_feed_type_has_a_profile(self):
        self.assertEqual(set(FEED_PROFILES), set(FeedType.values))

    def test_acceptable_band_must_enclose_optimal_band(self):
        with self.assertRaises(ValueError):
            ParameterCriteria(
                optimal=Band(Decimal('1'), Decimal('10')),
                acceptable=Band(Decimal('2'), Decimal('9')),
            )

    def test_score_weights_total_100(self):
        self.assertEqual(sum(SCORE_WEIGHTS.values()), 100)

    def test_unknown_feed_type_falls_back_to_other(self):
        self.assertIs(profile_for('nonsense'), FEED_PROFILES[FeedType.OTHER])
        self.assertIs(profile_for(None), FEED_PROFILES[FeedType.OTHER])

    def test_band_formatting_is_tidy(self):
        self.assertEqual(str(Band(Decimal('60'), Decimal('70'))), '60\u201370')
        self.assertEqual(str(Band(Decimal('3.7'), Decimal('4.2'))), '3.7\u20134.2')


class AssessmentEngineTests(SimpleTestCase):
    def test_ideal_sample_scores_100_and_is_within_criteria(self):
        assessment = assess_sample(sample_values())

        self.assertEqual(assessment.status, Status.WITHIN_CRITERIA)
        self.assertEqual(assessment.score, 100)
        self.assertTrue(all(level is Level.OPTIMAL for level in levels(assessment).values()))
        self.assertIn('illustrative', assessment.explanation)
        self.assertIn('not been scientifically validated', assessment.explanation)
        self.assertTrue(assessment.recommendations)

    def test_well_fermented_silage_is_not_penalised_for_low_ph(self):
        """Regression: the old single 5.0-7.5 pH range flagged good silage."""
        assessment = assess_sample(sample_values(ph_value=Decimal('3.90')))

        self.assertEqual(levels(assessment)['ph_value'], Level.OPTIMAL)
        self.assertEqual(assessment.status, Status.WITHIN_CRITERIA)

    def test_spoiled_silage_with_neutral_ph_is_flagged(self):
        """Regression: a pH of 6.5 passed under the old rules but signals failed fermentation."""
        assessment = assess_sample(sample_values(ph_value=Decimal('6.50')))

        self.assertEqual(levels(assessment)['ph_value'], Level.FLAGGED)
        self.assertEqual(assessment.status, Status.NEEDS_REVIEW)
        self.assertIn('fermentation', assessment.recommendations[0])

    def test_same_ph_is_judged_differently_per_feed_type(self):
        silage = assess_sample(sample_values(ph_value=Decimal('4.00')))
        hay = assess_sample(
            sample_values(
                feed_type=FeedType.HAY, ph_value=Decimal('4.00'), moisture=Decimal('12'), smell='fresh'
            )
        )

        self.assertEqual(levels(silage)['ph_value'], Level.OPTIMAL)
        self.assertEqual(levels(hay)['ph_value'], Level.FLAGGED)

    def test_borderline_values_give_half_credit_and_borderline_status(self):
        # 4.4 is acceptable (3.5-4.5) but outside optimal (3.7-4.2) for corn silage.
        assessment = assess_sample(sample_values(ph_value=Decimal('4.40')))

        self.assertEqual(levels(assessment)['ph_value'], Level.BORDERLINE)
        self.assertEqual(assessment.status, Status.BORDERLINE)
        self.assertEqual(assessment.score, 88)  # 100 - 25 / 2, rounded half up

    def test_range_boundaries_are_inclusive(self):
        for value, expected in (
            ('3.7', Level.OPTIMAL),
            ('4.2', Level.OPTIMAL),
            ('3.5', Level.BORDERLINE),
            ('4.5', Level.BORDERLINE),
            ('3.49', Level.FLAGGED),
            ('4.51', Level.FLAGGED),
        ):
            with self.subTest(ph=value):
                assessment = assess_sample(sample_values(ph_value=Decimal(value)))
                self.assertEqual(levels(assessment)['ph_value'], expected)

    def test_any_flagged_check_caps_the_score(self):
        assessment = assess_sample(sample_values(temperature=Decimal('55')))

        self.assertEqual(levels(assessment)['temperature'], Level.FLAGGED)
        self.assertEqual(assessment.status, Status.NEEDS_REVIEW)
        self.assertEqual(assessment.score, 69)  # 85 points, capped
        self.assertIn('ambient', assessment.recommendations[0])

    def test_visible_mold_forces_review_and_a_low_score(self):
        assessment = assess_sample(sample_values(mold_present=True))

        self.assertEqual(assessment.status, Status.NEEDS_REVIEW)
        self.assertEqual(assessment.score, 40)
        self.assertIn('mold', ' '.join(assessment.recommendations).lower())

    def test_every_flagged_parameter_gets_its_own_recommendation(self):
        assessment = assess_sample(
            sample_values(
                ph_value=Decimal('9.00'),
                moisture=Decimal('90.00'),
                temperature=Decimal('50.00'),
                smell='musty',
                mold_present=True,
            )
        )

        self.assertEqual(assessment.status, Status.NEEDS_REVIEW)
        self.assertEqual(len(assessment.recommendations), 5)
        self.assertTrue(all(level is Level.FLAGGED for level in levels(assessment).values()))
        self.assertEqual(assessment.score, 0 + 0 + 0 + 0 + 0)

    def test_slightly_sour_smell_depends_on_whether_feed_is_fermented(self):
        silage = assess_sample(sample_values(smell='slightly_sour'))
        hay = assess_sample(
            sample_values(
                feed_type=FeedType.HAY, moisture=Decimal('12'), ph_value=Decimal('6'), smell='slightly_sour'
            )
        )

        self.assertEqual(levels(silage)['smell'], Level.OPTIMAL)
        self.assertEqual(levels(hay)['smell'], Level.BORDERLINE)

    def test_other_and_unrecognised_smells_are_borderline(self):
        for smell in ('other', 'garlic'):
            with self.subTest(smell=smell):
                assessment = assess_sample(sample_values(smell=smell))
                self.assertEqual(levels(assessment)['smell'], Level.BORDERLINE)

    def test_missing_or_unusable_inputs_make_the_assessment_incomplete(self):
        assessment = assess_sample(
            sample_values(
                ph_value=None,
                moisture='not recorded',
                smell='',
                mold_present=None,
            )
        )

        self.assertEqual(assessment.status, Status.INCOMPLETE)
        self.assertIsNone(assessment.score)
        for label in ('pH', 'Moisture', 'Smell condition', 'Visible mold'):
            self.assertIn(label, assessment.explanation)
        self.assertIn('valid ph', ' '.join(assessment.recommendations).lower())

    def test_non_finite_numbers_are_treated_as_missing(self):
        for bad in (float('nan'), float('inf'), Decimal('NaN'), True):
            with self.subTest(value=bad):
                assessment = assess_sample(sample_values(ph_value=bad))
                self.assertEqual(levels(assessment)['ph_value'], Level.MISSING)

    def test_unknown_feed_type_still_produces_an_assessment(self):
        assessment = assess_sample(
            sample_values(feed_type='mystery', ph_value=Decimal('6.0'), moisture=Decimal('50'), smell='fresh')
        )

        self.assertEqual(assessment.status, Status.WITHIN_CRITERIA)

    def test_findings_serialise_to_json_friendly_dicts(self):
        fields = assess_sample(sample_values()).as_model_fields()

        self.assertEqual(len(fields['findings']), 5)
        self.assertEqual(fields['findings'][0]['level'], 'optimal')
        self.assertEqual(sum(f['max_points'] for f in fields['findings']), 100)


class AssessAndStoreTests(TestCase):
    def test_creates_then_updates_a_single_result_with_findings(self):
        sample = make_sample(make_farmer())

        first = assess_and_store(sample)
        sample.mold_present = True
        sample.save()
        second = assess_and_store(sample)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(TestResult.objects.filter(sample=sample).count(), 1)
        second.refresh_from_db()
        self.assertEqual(second.quality_status, Status.NEEDS_REVIEW)
        self.assertEqual(second.quality_score, 40)
        self.assertEqual(len(second.findings), 5)
