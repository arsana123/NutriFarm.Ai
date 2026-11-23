"""Small helpers shared by the test modules."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from testing.models import FeedSample

PASSWORD = 'StrongFarmPassword!829'


def make_farmer(username='farmer', **extra):
    return get_user_model().objects.create_user(username=username, password=PASSWORD, **extra)


def make_sample(farmer, **overrides):
    """Create a well-fermented corn silage sample unless overridden."""
    values = {
        'sample_name': 'Corn silage A',
        'feed_type': FeedSample.FeedType.CORN_SILAGE,
        'collection_date': timezone.localdate(),
        'ph_value': Decimal('4.00'),
        'moisture': Decimal('65.00'),
        'temperature': Decimal('20.00'),
        'smell': FeedSample.Smell.SLIGHTLY_SOUR,
        'mold_present': False,
    }
    values.update(overrides)
    return FeedSample.objects.create(farmer=farmer, **values)
