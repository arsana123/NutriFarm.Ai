from decimal import Decimal

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from testing.models import FeedSample, TestResult


class FeedSampleDashboardTests(TestCase):
    def setUp(self):
        self.farmer = User.objects.create_user(
            username='farmer-one',
            password='StrongFarmPassword!829',
            first_name='Avery',
            last_name='Farmer',
        )
        self.other_farmer = User.objects.create_user(
            username='farmer-two',
            password='StrongFarmPassword!829',
        )

    def create_sample(self, farmer, sample_name='Fresh silage'):
        return FeedSample.objects.create(
            farmer=farmer,
            sample_name=sample_name,
            feed_type=FeedSample.FeedType.SILAGE,
            ph_value=Decimal('5.20'),
            moisture=Decimal('62.50'),
            temperature=Decimal('19.00'),
            smell='fresh',
            mold_present=False,
        )

    def test_dashboard_requires_login_and_displays_empty_counts(self):
        response = self.client.get(reverse('testing:dashboard'))
        self.assertRedirects(
            response,
            f'{reverse("testing:login")}?next={reverse("testing:dashboard")}',
        )

        self.client.force_login(self.farmer)
        response = self.client.get(reverse('testing:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome, Avery Farmer.')
        self.assertContains(response, 'TOTAL SAMPLES')
        self.assertContains(response, 'TESTED SAMPLES')
        self.assertContains(response, reverse('testing:sample_create'))
        self.assertContains(response, reverse('testing:sample_history'))
        self.assertEqual(response.context['total_samples'], 0)
        self.assertEqual(response.context['total_tested'], 0)
        self.assertQuerySetEqual(response.context['recent_samples'], [])

    def test_dashboard_counts_only_owned_database_records(self):
        sample = self.create_sample(self.farmer)
        TestResult.objects.create(
            sample=sample,
            quality_score=84,
            quality_status='Good',
            recommendations='Continue regular checks.',
        )
        self.create_sample(self.other_farmer, 'Other farmer sample')
        self.client.force_login(self.farmer)

        response = self.client.get(reverse('testing:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_samples'], 1)
        self.assertEqual(response.context['total_tested'], 1)
        self.assertEqual(list(response.context['recent_samples']), [sample])
        self.assertContains(response, 'Fresh silage')
        self.assertNotContains(response, 'Other farmer sample')
        self.assertEqual(sample.test_result.quality_status, 'Good')
        self.assertEqual(sample.test_result.quality_score, 84)

    def test_sample_detail_is_private_to_its_farmer(self):
        sample = self.create_sample(self.farmer)
        url = reverse('testing:sample_detail', args=[sample.pk])

        anonymous_response = self.client.get(url)
        self.assertRedirects(
            anonymous_response,
            f'{reverse("testing:login")}?next={url}',
        )

        self.client.force_login(self.other_farmer)
        self.assertEqual(self.client.get(url).status_code, 404)

        self.client.force_login(self.farmer)
        own_response = self.client.get(url)
        self.assertEqual(own_response.status_code, 200)
        self.assertContains(own_response, 'Fresh silage')

    def test_admin_has_both_models_registered_and_changelists_are_available(self):
        self.assertTrue(admin.site.is_registered(FeedSample))
        self.assertTrue(admin.site.is_registered(TestResult))
        admin_user = User.objects.create_superuser(
            username='site-admin',
            email='admin@example.com',
            password='StrongFarmPassword!829',
        )
        self.client.force_login(admin_user)

        sample_response = self.client.get('/admin/testing/feedSample/'.lower())
        result_response = self.client.get('/admin/testing/testresult/')

        self.assertEqual(sample_response.status_code, 200)
        self.assertEqual(result_response.status_code, 200)

    def test_admin_can_add_change_and_delete_sample_records(self):
        admin_user = User.objects.create_superuser(
            username='crud-admin',
            email='crud-admin@example.com',
            password='StrongFarmPassword!829',
        )
        self.client.force_login(admin_user)
        sample_data = {
            'sample_name': 'Admin sample',
            'farmer': self.farmer.pk,
            'feed_type': FeedSample.FeedType.SILAGE,
            'collection_date': timezone.localdate().isoformat(),
            'ph_value': '5.20',
            'moisture': '62.50',
            'temperature': '19.00',
            'smell': 'fresh',
            # Management form for the read-only assessment inline, as a browser would send it.
            'test_result-TOTAL_FORMS': '0',
            'test_result-INITIAL_FORMS': '0',
            'test_result-MIN_NUM_FORMS': '0',
            'test_result-MAX_NUM_FORMS': '1',
            '_save': 'Save',
        }

        response = self.client.post(reverse('admin:testing_feedsample_add'), sample_data)
        self.assertEqual(
            response.status_code,
            302,
            response.context['adminform'].form.errors if response.context else response.content[:2000],
        )
        sample = FeedSample.objects.get(sample_name='Admin sample')

        sample_data['sample_name'] = 'Updated sample'
        response = self.client.post(
            reverse('admin:testing_feedsample_change', args=[sample.pk]),
            sample_data,
        )
        self.assertEqual(response.status_code, 302)
        sample.refresh_from_db()
        self.assertEqual(sample.sample_name, 'Updated sample')

        response = self.client.post(
            reverse('admin:testing_feedsample_delete', args=[sample.pk]),
            {'post': 'yes'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(FeedSample.objects.filter(pk=sample.pk).exists())
