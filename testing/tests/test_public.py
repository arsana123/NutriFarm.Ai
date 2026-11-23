from django.test import TestCase, override_settings
from django.urls import reverse

from testing.models import ContactMessage


class PublicPageTests(TestCase):
    def test_existing_homepage_and_information_pages_load(self):
        pages = (
            ('core:home', 'Know what'),
            ('testing:about', 'ABOUT NUTRIFARM AI'),
            ('testing:features', 'PLATFORM FEATURES'),
            ('testing:contact', 'CONTACT US'),
        )

        for url_name, expected_text in pages:
            with self.subTest(page=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected_text)

    def test_contact_form_stores_message_and_confirms(self):
        response = self.client.post(
            reverse('testing:contact'),
            {'name': 'Farmer', 'email': 'farmer@example.com', 'message': 'Hello there'},
            follow=True,
        )

        self.assertRedirects(response, reverse('testing:contact'))
        self.assertContains(response, 'Your message has been received')
        message = ContactMessage.objects.get()
        self.assertEqual(message.email, 'farmer@example.com')

    def test_contact_form_rejects_invalid_input_and_honeypot(self):
        invalid = self.client.post(reverse('testing:contact'), {'name': 'Farmer', 'email': 'nope'})
        spam = self.client.post(
            reverse('testing:contact'),
            {'name': 'Bot', 'email': 'bot@example.com', 'message': 'Buy now', 'website': 'http://spam'},
        )

        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(spam.status_code, 200)
        self.assertFalse(ContactMessage.objects.exists())

    @override_settings(DEBUG=False)
    def test_unknown_page_returns_friendly_404(self):
        response = self.client.get('/not-a-page/', HTTP_HOST='localhost')

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'We couldn’t find that page.', status_code=404)
