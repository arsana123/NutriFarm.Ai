from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class FarmerAccountTests(TestCase):
    def registration_data(self, **overrides):
        data = {
            'full_name': 'River Farmer',
            'username': 'river',
            'email': 'river@example.com',
            'password1': 'StrongFarmPassword!829',
            'password2': 'StrongFarmPassword!829',
        }
        data.update(overrides)
        return data

    def test_registration_creates_hashed_user_and_logs_in(self):
        response = self.client.post(
            reverse('testing:register'),
            self.registration_data(),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse('testing:dashboard'))
        self.assertContains(response, 'Welcome, River Farmer.')
        user = User.objects.get(username='river')
        self.assertEqual(user.email, 'river@example.com')
        self.assertEqual(user.get_full_name(), 'River Farmer')
        self.assertNotEqual(user.password, 'StrongFarmPassword!829')
        self.assertTrue(user.check_password('StrongFarmPassword!829'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_registration_rejects_mismatched_passwords(self):
        response = self.client.post(
            reverse('testing:register'),
            self.registration_data(password2='DifferentPassword!829'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='river').exists())
        self.assertIn('password2', response.context['form'].errors)

    def test_registration_and_login_pages_include_csrf_tokens(self):
        for url_name in ('testing:register', 'testing:login'):
            with self.subTest(page=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'csrfmiddlewaretoken')

    def test_login_and_logout_use_authentication_session(self):
        user = User.objects.create_user(username='river', password='StrongFarmPassword!829')

        response = self.client.post(
            reverse('testing:login'),
            {'username': 'river', 'password': 'StrongFarmPassword!829'},
        )
        self.assertRedirects(response, reverse('testing:dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

        response = self.client.post(reverse('testing:logout'))
        self.assertRedirects(response, reverse('core:home'))
        dashboard_response = self.client.get(reverse('testing:dashboard'))
        self.assertRedirects(
            dashboard_response,
            f'{reverse("testing:login")}?next={reverse("testing:dashboard")}',
        )

    def test_invalid_login_does_not_authenticate(self):
        User.objects.create_user(username='river', password='StrongFarmPassword!829')

        response = self.client.post(
            reverse('testing:login'),
            {'username': 'river', 'password': 'incorrect-password'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_requires_post(self):
        response = self.client.get(reverse('testing:logout'))

        self.assertEqual(response.status_code, 405)
