import csv
import io
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from testing.models import FeedSample, TestResult
from testing.services import assess_and_store

from .factories import PASSWORD, make_farmer, make_sample


class SampleEditDeleteTests(TestCase):
    def setUp(self):
        self.farmer = make_farmer('editor')
        self.other = make_farmer('intruder')
        self.sample = make_sample(self.farmer)
        self.client.force_login(self.farmer)

    def form_data(self, **overrides):
        data = {
            'sample_name': 'Renamed sample',
            'feed_type': FeedSample.FeedType.CORN_SILAGE,
            'collection_date': timezone.localdate().isoformat(),
            'ph_value': '4.00',
            'moisture': '65.00',
            'temperature': '20.00',
            'smell': 'slightly_sour',
            'observations': '',
        }
        data.update(overrides)
        return data

    def test_edit_form_is_prefilled_including_the_date(self):
        response = self.client.get(reverse('testing:sample_update', args=[self.sample.pk]))

        self.assertContains(response, f'value="{self.sample.collection_date.isoformat()}"')
        self.assertContains(response, 'Corn silage A')

    def test_editing_updates_the_sample(self):
        response = self.client.post(
            reverse('testing:sample_update', args=[self.sample.pk]),
            self.form_data(),
        )

        self.assertRedirects(response, reverse('testing:sample_detail', args=[self.sample.pk]))
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.sample_name, 'Renamed sample')
        self.assertFalse(TestResult.objects.exists())

    def test_editing_an_assessed_sample_refreshes_its_assessment(self):
        assess_and_store(self.sample)
        self.assertEqual(self.sample.test_result.quality_score, 100)

        self.client.post(
            reverse('testing:sample_update', args=[self.sample.pk]),
            self.form_data(ph_value='6.50'),
        )

        result = TestResult.objects.get(sample=self.sample)
        self.assertEqual(result.quality_status, TestResult.Status.NEEDS_REVIEW)

    def test_invalid_edit_shows_errors_and_changes_nothing(self):
        response = self.client.post(
            reverse('testing:sample_update', args=[self.sample.pk]),
            self.form_data(ph_value='15'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'is-invalid')
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.ph_value, Decimal('4.00'))

    def test_other_farmer_cannot_edit_or_delete(self):
        self.client.force_login(self.other)
        for name in ('testing:sample_update', 'testing:sample_delete'):
            url = reverse(name, args=[self.sample.pk])
            with self.subTest(view=name):
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url, self.form_data()).status_code, 404)
        self.assertTrue(FeedSample.objects.filter(pk=self.sample.pk).exists())

    def test_delete_requires_confirmation_then_removes_sample_and_result(self):
        assess_and_store(self.sample)
        url = reverse('testing:sample_delete', args=[self.sample.pk])

        confirm = self.client.get(url)
        self.assertContains(confirm, 'Yes, delete this sample')
        self.assertTrue(FeedSample.objects.filter(pk=self.sample.pk).exists())

        response = self.client.post(url)
        self.assertRedirects(response, reverse('testing:sample_history'))
        self.assertFalse(FeedSample.objects.filter(pk=self.sample.pk).exists())
        self.assertFalse(TestResult.objects.exists())


class SampleHistoryTests(TestCase):
    def setUp(self):
        self.farmer = make_farmer('historian')
        self.client.force_login(self.farmer)
        self.url = reverse('testing:sample_history')

    def test_filters_by_feed_type_and_ignores_invalid_values(self):
        make_sample(self.farmer, sample_name='Hay bale', feed_type=FeedSample.FeedType.HAY)
        make_sample(self.farmer, sample_name='Corn pile')

        hay = self.client.get(self.url, {'feed_type': 'hay'})
        junk = self.client.get(self.url, {'feed_type': 'not-a-type', 'status': 'bogus'})

        self.assertContains(hay, 'Hay bale')
        self.assertNotContains(hay, 'Corn pile')
        self.assertContains(junk, 'Hay bale')
        self.assertContains(junk, 'Corn pile')

    def test_filters_by_assessment_status(self):
        assessed = make_sample(self.farmer, sample_name='Assessed one')
        make_sample(self.farmer, sample_name='Waiting one')
        assess_and_store(assessed)

        pending = self.client.get(self.url, {'status': 'unassessed'})
        done = self.client.get(self.url, {'status': TestResult.Status.WITHIN_CRITERIA})

        self.assertContains(pending, 'Waiting one')
        self.assertNotContains(pending, 'Assessed one')
        self.assertContains(done, 'Assessed one')
        self.assertNotContains(done, 'Waiting one')

    def test_no_matches_shows_filter_specific_empty_state(self):
        make_sample(self.farmer)

        response = self.client.get(self.url, {'feed_type': 'hay'})

        self.assertContains(response, 'No samples match these filters')

    def test_history_is_paginated_and_pagination_keeps_filters(self):
        for number in range(12):
            make_sample(self.farmer, sample_name=f'Sample {number:02d}')

        first = self.client.get(self.url, {'feed_type': 'corn_silage'})
        second = self.client.get(self.url, {'feed_type': 'corn_silage', 'page': 2})

        self.assertEqual(len(first.context['samples']), 10)
        self.assertEqual(len(second.context['samples']), 2)
        self.assertContains(first, 'feed_type=corn_silage&amp;page=2')


class CsvExportTests(TestCase):
    def setUp(self):
        self.farmer = make_farmer('exporter')
        self.client.force_login(self.farmer)
        self.url = reverse('testing:sample_export_csv')

    def rows(self, response):
        return list(csv.reader(io.StringIO(b''.join(response.streaming_content).decode())))

    def first_record(self, response):
        header, first, *_ = self.rows(response)
        return dict(zip(header, first, strict=True))

    def test_export_contains_only_own_samples_and_assessment_data(self):
        mine = make_sample(self.farmer, sample_name='Mine')
        make_sample(make_farmer('someone-else'), sample_name='Not mine')
        assess_and_store(mine)

        response = self.client.get(self.url)
        rows = self.rows(response)

        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertEqual(len(rows), 2)  # header + one sample
        record = dict(zip(rows[0], rows[1], strict=True))
        self.assertEqual(record['Sample'], 'Mine')
        self.assertEqual(record['Feed type'], 'Corn silage')
        self.assertEqual(record['Status'], 'Within prototype criteria')
        self.assertEqual(record['Score'], '100')

    def test_unassessed_samples_are_labelled(self):
        make_sample(self.farmer)

        record = self.first_record(self.client.get(self.url))

        self.assertEqual(record['Status'], 'Not assessed')
        self.assertEqual(record['Score'], '')

    def test_spreadsheet_formulas_in_free_text_are_neutralised(self):
        make_sample(
            self.farmer,
            sample_name='=HYPERLINK("http://evil")',
            observations='+cmd|calc',
            temperature=Decimal('-5.00'),
        )

        record = self.first_record(self.client.get(self.url))

        self.assertEqual(record['Sample'], '\'=HYPERLINK("http://evil")')
        self.assertEqual(record['Observations'], "'+cmd|calc")
        self.assertEqual(record['Temperature C'], '-5.00')  # real numbers are left alone

    def test_export_requires_login(self):
        self.client.logout()

        self.assertEqual(self.client.get(self.url).status_code, 302)


class DashboardStatsTests(TestCase):
    def test_dashboard_shows_review_count_and_average_score(self):
        farmer = make_farmer('stats')
        self.client.force_login(farmer)
        assess_and_store(make_sample(farmer, sample_name='Perfect'))  # 100
        assess_and_store(make_sample(farmer, sample_name='Moldy', mold_present=True))  # 40
        make_sample(farmer, sample_name='Pending')

        response = self.client.get(reverse('testing:dashboard'))

        self.assertEqual(response.context['total_samples'], 3)
        self.assertEqual(response.context['total_tested'], 2)
        self.assertEqual(response.context['needs_review_count'], 1)
        self.assertEqual(response.context['average_score'], 70)


class LoginRedirectTests(TestCase):
    def setUp(self):
        self.farmer = make_farmer('returning')

    def test_login_returns_to_the_page_that_required_it(self):
        target = reverse('testing:sample_history')

        response = self.client.post(
            f'{reverse("testing:login")}?next={target}',
            {'username': 'returning', 'password': PASSWORD, 'next': target},
        )

        self.assertRedirects(response, target)

    def test_login_ignores_external_redirect_targets(self):
        response = self.client.post(
            reverse('testing:login'),
            {'username': 'returning', 'password': PASSWORD, 'next': 'https://evil.example/'},
        )

        self.assertRedirects(response, reverse('testing:dashboard'))


class RegistrationTests(TestCase):
    def test_duplicate_email_is_rejected_case_insensitively(self):
        make_farmer('first', email='Taken@Example.com')

        response = self.client.post(
            reverse('testing:register'),
            {
                'full_name': 'Second Farmer',
                'username': 'second',
                'email': 'taken@example.com',
                'password1': PASSWORD,
                'password2': PASSWORD,
            },
        )

        self.assertContains(response, 'already exists')
        self.assertFalse(
            FeedSample._meta.apps.get_model('auth', 'User').objects.filter(username='second').exists()
        )


class FormValidationTests(TestCase):
    def test_database_constraints_back_up_form_validation(self):
        from django.db import IntegrityError, transaction

        farmer = make_farmer('constraints')
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_sample(farmer, ph_value=Decimal('15.00'))
