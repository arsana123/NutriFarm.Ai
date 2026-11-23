from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from testing.models import FeedSample


class SampleManagementTests(TestCase):
    def setUp(self):
        self.farmer = User.objects.create_user(
            username='sample-farmer',
            password='StrongFarmPassword!829',
        )
        self.other_farmer = User.objects.create_user(
            username='other-sample-farmer',
            password='StrongFarmPassword!829',
        )
        self.client.force_login(self.farmer)

    def sample_data(self, **overrides):
        data = {
            'sample_name': 'Morning field sample',
            'feed_type': FeedSample.FeedType.GREEN_FODDER,
            'collection_date': timezone.localdate().isoformat(),
            'ph_value': '7.10',
            'moisture': '75.50',
            'temperature': '20.50',
            'smell': 'fresh',
            'observations': 'Cut from the north paddock.',
            'mold_present': 'on',
        }
        data.update(overrides)
        return data

    def test_submit_sample_persists_owner_and_shows_details_after_refresh(self):
        response = self.client.post(
            reverse('testing:sample_create'),
            self.sample_data(),
        )

        sample = FeedSample.objects.get(sample_name='Morning field sample')
        self.assertRedirects(
            response,
            reverse('testing:sample_detail', args=[sample.pk]),
        )
        self.assertEqual(sample.farmer, self.farmer)
        self.assertEqual(sample.collection_date, timezone.localdate())
        self.assertEqual(sample.ph_value, Decimal('7.10'))
        self.assertEqual(sample.moisture, Decimal('75.50'))
        self.assertEqual(sample.temperature, Decimal('20.50'))
        self.assertTrue(sample.mold_present)
        self.assertEqual(sample.observations, 'Cut from the north paddock.')

        refreshed_response = self.client.get(
            reverse('testing:sample_detail', args=[sample.pk]),
        )
        self.assertEqual(refreshed_response.status_code, 200)
        self.assertContains(refreshed_response, 'Cut from the north paddock.')
        self.assertContains(refreshed_response, 'Morning field sample')

        dashboard_response = self.client.get(reverse('testing:dashboard'))
        self.assertEqual(dashboard_response.context['total_samples'], 1)

    def test_posted_farmer_id_cannot_change_sample_owner(self):
        response = self.client.post(
            reverse('testing:sample_create'),
            self.sample_data(farmer=str(self.other_farmer.pk)),
        )

        self.assertEqual(response.status_code, 302)
        sample = FeedSample.objects.get(sample_name='Morning field sample')
        self.assertEqual(sample.farmer, self.farmer)

    def test_submission_rejects_invalid_values_and_future_dates(self):
        invalid_inputs = (
            ('ph_value', '14.01'),
            ('ph_value', '-0.01'),
            ('moisture', '100.01'),
            ('moisture', '-0.01'),
            ('temperature', '80.01'),
            ('temperature', '-20.01'),
            ('temperature', 'not-a-number'),
            ('collection_date', (timezone.localdate() + timedelta(days=1)).isoformat()),
            ('sample_name', ''),
        )

        for field_name, invalid_value in invalid_inputs:
            with self.subTest(field=field_name, value=invalid_value):
                response = self.client.post(
                    reverse('testing:sample_create'),
                    self.sample_data(**{field_name: invalid_value}),
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(field_name, response.context['form'].errors)
                self.assertFalse(FeedSample.objects.filter(sample_name='Morning field sample').exists())

    def test_required_sample_fields_cannot_be_empty(self):
        required_fields = (
            'sample_name',
            'feed_type',
            'collection_date',
            'ph_value',
            'moisture',
            'temperature',
            'smell',
        )
        response = self.client.post(
            reverse('testing:sample_create'),
            self.sample_data(**dict.fromkeys(required_fields, '')),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(set(required_fields).issubset(response.context['form'].errors))
        self.assertFalse(FeedSample.objects.exists())

    def test_sample_form_requires_login_and_includes_csrf_token(self):
        self.client.logout()
        response = self.client.get(reverse('testing:sample_create'))
        self.assertRedirects(
            response,
            f'{reverse("testing:login")}?next={reverse("testing:sample_create")}',
        )

        self.client.force_login(self.farmer)
        response = self.client.get(reverse('testing:sample_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_csrf_middleware_rejects_sample_post_without_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.farmer)

        response = csrf_client.post(
            reverse('testing:sample_create'),
            self.sample_data(),
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(FeedSample.objects.exists())

    def test_history_shows_only_the_current_farmers_samples(self):
        own_sample = FeedSample.objects.create(
            farmer=self.farmer,
            sample_name='My paddock sample',
            feed_type=FeedSample.FeedType.DRY_FODDER,
            collection_date=timezone.localdate(),
            ph_value=Decimal('6.20'),
            moisture=Decimal('20.00'),
            temperature=Decimal('18.00'),
            smell='fresh',
        )
        FeedSample.objects.create(
            farmer=self.other_farmer,
            sample_name='Private other sample',
            feed_type=FeedSample.FeedType.SILAGE,
            collection_date=timezone.localdate(),
            ph_value=Decimal('5.20'),
            moisture=Decimal('62.50'),
            temperature=Decimal('19.00'),
            smell='fresh',
        )

        response = self.client.get(reverse('testing:sample_history'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['samples']), [own_sample])
        self.assertContains(response, 'My paddock sample')
        self.assertNotContains(response, 'Private other sample')

    def test_history_displays_helpful_empty_state(self):
        response = self.client.get(reverse('testing:sample_history'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No samples yet')
        self.assertContains(response, 'Submit your first sample')

    def test_other_farmer_cannot_open_sample_details(self):
        sample = FeedSample.objects.create(
            farmer=self.other_farmer,
            sample_name='Not your sample',
            feed_type=FeedSample.FeedType.SILAGE,
            collection_date=timezone.localdate(),
            ph_value=Decimal('5.20'),
            moisture=Decimal('62.50'),
            temperature=Decimal('19.00'),
            smell='fresh',
        )

        response = self.client.get(
            reverse('testing:sample_detail', args=[sample.pk]),
        )

        self.assertEqual(response.status_code, 404)
