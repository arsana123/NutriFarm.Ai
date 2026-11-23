from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from testing.models import FeedSample, TestResult


class CompleteFarmerWorkflowTests(TestCase):
    def registration_data(self, username, email, full_name):
        return {
            'full_name': full_name,
            'username': username,
            'email': email,
            'password1': 'StrongFarmPassword!829',
            'password2': 'StrongFarmPassword!829',
        }

    def test_two_farmer_workflow_from_registration_to_logout(self):
        homepage = self.client.get(reverse('core:home'))
        self.assertEqual(homepage.status_code, 200)
        self.assertContains(homepage, reverse('testing:register'))

        registration = self.client.post(
            reverse('testing:register'),
            self.registration_data('complete-farmer', 'complete@example.com', 'Casey Farmer'),
        )
        self.assertRedirects(registration, reverse('testing:dashboard'))

        dashboard = self.client.get(reverse('testing:dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        for destination in ('testing:sample_create', 'testing:sample_history', 'testing:logout'):
            self.assertContains(dashboard, reverse(destination))

        sample_response = self.client.post(
            reverse('testing:sample_create'),
            {
                'sample_name': 'Full journey sample',
                'feed_type': FeedSample.FeedType.SILAGE,
                'collection_date': timezone.localdate().isoformat(),
                'ph_value': '6.20',
                'moisture': '58.00',
                'temperature': '21.00',
                'smell': 'fresh',
                'mold_present': '',
                'observations': 'Test workflow record',
            },
        )
        sample = FeedSample.objects.get(sample_name='Full journey sample')
        self.assertRedirects(
            sample_response,
            reverse('testing:sample_detail', args=[sample.pk]),
        )

        history = self.client.get(reverse('testing:sample_history'))
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, 'Full journey sample')
        self.assertContains(history, reverse('testing:sample_detail', args=[sample.pk]))

        detail = self.client.get(reverse('testing:sample_detail', args=[sample.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, reverse('testing:evaluate_sample', args=[sample.pk]))

        evaluation = self.client.post(reverse('testing:evaluate_sample', args=[sample.pk]))
        self.assertRedirects(evaluation, reverse('testing:sample_result', args=[sample.pk]))
        result_page = self.client.get(reverse('testing:sample_result', args=[sample.pk]))
        self.assertEqual(result_page.status_code, 200)
        self.assertEqual(TestResult.objects.filter(sample=sample).count(), 1)

        updated_dashboard = self.client.get(reverse('testing:dashboard'))
        self.assertEqual(updated_dashboard.context['total_samples'], 1)
        self.assertEqual(updated_dashboard.context['total_tested'], 1)

        logout_response = self.client.post(reverse('testing:logout'))
        self.assertRedirects(logout_response, reverse('core:home'))
        self.assertRedirects(
            self.client.get(reverse('testing:dashboard')),
            f'{reverse("testing:login")}?next={reverse("testing:dashboard")}',
        )

        second_farmer = User.objects.create_user(
            username='second-farmer',
            password='SecondFarmerPassword!829',
        )
        login_response = self.client.post(
            reverse('testing:login'),
            {'username': second_farmer.username, 'password': 'SecondFarmerPassword!829'},
        )
        self.assertRedirects(login_response, reverse('testing:dashboard'))
        self.assertEqual(
            self.client.get(reverse('testing:dashboard')).context['total_samples'],
            0,
        )
        self.assertEqual(
            self.client.get(reverse('testing:sample_detail', args=[sample.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse('testing:sample_result', args=[sample.pk])).status_code,
            404,
        )
