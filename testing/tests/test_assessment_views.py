from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from testing.models import FeedSample, TestResult


class AssessmentViewTests(TestCase):
    def setUp(self):
        self.farmer = User.objects.create_user(
            username='assessment-farmer',
            password='StrongFarmPassword!829',
        )
        self.other_farmer = User.objects.create_user(
            username='other-assessment-farmer',
            password='StrongFarmPassword!829',
        )
        self.sample = FeedSample.objects.create(
            farmer=self.farmer,
            sample_name='Assessment silage',
            feed_type=FeedSample.FeedType.SILAGE,
            collection_date=timezone.localdate(),
            ph_value=Decimal('4.20'),
            moisture=Decimal('60.00'),
            temperature=Decimal('22.00'),
            smell='fresh',
            mold_present=False,
        )

    def test_evaluate_persists_result_and_re_evaluation_updates_it(self):
        self.client.force_login(self.farmer)
        evaluate_url = reverse('testing:evaluate_sample', args=[self.sample.pk])
        result_url = reverse('testing:sample_result', args=[self.sample.pk])

        first_response = self.client.post(evaluate_url)
        self.assertRedirects(first_response, result_url)
        result = TestResult.objects.get(sample=self.sample)
        first_id = result.pk
        first_tested_at = result.tested_at
        self.assertEqual(result.quality_status, 'Within prototype criteria')
        self.assertEqual(result.quality_score, 100)
        self.assertIn('illustrative', result.assessment_explanation)

        self.sample.mold_present = True
        self.sample.save(update_fields=['mold_present'])
        later_time = first_tested_at + timedelta(minutes=1)
        with patch('django.utils.timezone.now', return_value=later_time):
            second_response = self.client.post(evaluate_url)

        self.assertRedirects(second_response, result_url)
        result.refresh_from_db()
        self.assertEqual(TestResult.objects.filter(sample=self.sample).count(), 1)
        self.assertEqual(result.pk, first_id)
        self.assertEqual(result.quality_status, 'Needs review')
        self.assertEqual(result.tested_at, later_time)

    def test_sample_detail_and_result_page_show_assessment(self):
        self.client.force_login(self.farmer)
        self.client.post(reverse('testing:evaluate_sample', args=[self.sample.pk]))

        detail_response = self.client.get(reverse('testing:sample_detail', args=[self.sample.pk]))
        result_response = self.client.get(reverse('testing:sample_result', args=[self.sample.pk]))

        self.assertContains(detail_response, 'Within prototype criteria')
        self.assertContains(
            detail_response,
            reverse('testing:sample_result', args=[self.sample.pk]),
        )
        self.assertContains(detail_response, 'Mold present:')
        self.assertContains(result_response, 'PROTOTYPE CATEGORY')
        self.assertContains(result_response, 'not scientifically validated')
        self.assertContains(result_response, self.sample.collection_date.strftime('Collected %b '))
        self.assertNotContains(result_response, '{{')

    def test_unevaluated_result_page_has_evaluate_action_and_detail_message(self):
        self.client.force_login(self.farmer)

        result_response = self.client.get(reverse('testing:sample_result', args=[self.sample.pk]))
        detail_response = self.client.get(reverse('testing:sample_detail', args=[self.sample.pk]))

        self.assertContains(result_response, 'This sample has not been assessed yet.')
        self.assertContains(detail_response, 'This sample has not been assessed yet.')
        self.assertContains(result_response, reverse('testing:evaluate_sample', args=[self.sample.pk]))

    def test_assessment_is_post_only_and_uses_csrf(self):
        self.client.force_login(self.farmer)
        evaluate_url = reverse('testing:evaluate_sample', args=[self.sample.pk])
        self.assertEqual(self.client.get(evaluate_url).status_code, 405)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.farmer)
        response = csrf_client.post(evaluate_url)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(TestResult.objects.filter(sample=self.sample).exists())

    def test_user_cannot_evaluate_or_view_another_users_result(self):
        self.client.force_login(self.other_farmer)
        result_url = reverse('testing:sample_result', args=[self.sample.pk])
        evaluate_url = reverse('testing:evaluate_sample', args=[self.sample.pk])

        self.assertEqual(self.client.get(result_url).status_code, 404)
        self.assertEqual(self.client.post(evaluate_url).status_code, 404)
        self.assertFalse(TestResult.objects.filter(sample=self.sample).exists())

    def test_assessment_route_requires_authentication(self):
        response = self.client.post(
            reverse('testing:evaluate_sample', args=[self.sample.pk]),
        )

        self.assertRedirects(
            response,
            f'{reverse("testing:login")}?next={reverse("testing:evaluate_sample", args=[self.sample.pk])}',
        )
