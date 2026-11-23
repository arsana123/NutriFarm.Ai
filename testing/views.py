import csv

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import ContactForm, FarmerRegistrationForm, FeedSampleForm
from .models import FeedSample, TestResult
from .services import assess_and_store

UNASSESSED = 'unassessed'


# --------------------------------------------------------------------------
# Public pages
# --------------------------------------------------------------------------


def about(request: HttpRequest) -> HttpResponse:
    """Show information about the NutriFarm AI project."""
    return render(request, 'testing/about.html')


def features(request: HttpRequest) -> HttpResponse:
    """Show the platform's features."""
    return render(request, 'testing/features.html')


def contact(request: HttpRequest) -> HttpResponse:
    """Show the contact form and store submitted messages for staff to read in admin."""
    form = ContactForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Thank you. Your message has been received.')
        return redirect('testing:contact')
    return render(request, 'testing/contact.html', {'form': form})


def page_not_found(request: HttpRequest, exception: Exception) -> HttpResponse:
    """Render the project's friendly 404 page when DEBUG is disabled."""
    return render(request, '404.html', status=404)


# --------------------------------------------------------------------------
# Accounts (login/logout use Django's class-based views; see urls.py)
# --------------------------------------------------------------------------


def register(request: HttpRequest) -> HttpResponse:
    """Validate and create a farmer account using Django's User model."""
    if request.user.is_authenticated:
        return redirect('testing:dashboard')

    form = FarmerRegistrationForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, 'Your farmer account has been created.')
        return redirect('testing:dashboard')

    return render(request, 'testing/register.html', {'form': form})


# --------------------------------------------------------------------------
# Samples
# --------------------------------------------------------------------------


def _owned_samples(request: HttpRequest):
    """Samples belonging to the signed-in farmer, with results preloaded."""
    return FeedSample.objects.filter(farmer=request.user).select_related('test_result')


def _get_owned_sample(request: HttpRequest, sample_id: int) -> FeedSample:
    """Return the farmer's sample or raise 404, so other farmers' IDs reveal nothing."""
    return get_object_or_404(_owned_samples(request), pk=sample_id)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """Show summary figures and recent samples belonging to the signed-in farmer."""
    samples = _owned_samples(request)
    stats = samples.aggregate(
        total=Count('pk'),
        tested=Count('test_result'),
        needs_review=Count(
            'test_result', filter=Q(test_result__quality_status=TestResult.Status.NEEDS_REVIEW)
        ),
        average_score=Avg('test_result__quality_score'),
    )
    context = {
        'farmer_name': request.user.get_full_name() or request.user.username,
        'total_samples': stats['total'],
        'total_tested': stats['tested'],
        'needs_review_count': stats['needs_review'],
        'average_score': round(stats['average_score']) if stats['average_score'] is not None else None,
        'recent_samples': samples[:5],
    }
    return render(request, 'testing/dashboard.html', context)


@login_required
def sample_create(request: HttpRequest) -> HttpResponse:
    """Validate and save a sample owned by the logged-in farmer."""
    form = FeedSampleForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        sample = form.save(commit=False)
        sample.farmer = request.user
        sample.save()
        messages.success(request, 'Your sample was saved successfully.')
        return redirect('testing:sample_detail', sample_id=sample.pk)

    return render(request, 'testing/sample_form.html', {'form': form, 'is_edit': False})


@login_required
def sample_update(request: HttpRequest, sample_id: int) -> HttpResponse:
    """Edit an owned sample. An existing assessment is refreshed so it is never stale."""
    sample = _get_owned_sample(request, sample_id)
    had_result = sample.result is not None
    form = FeedSampleForm(request.POST if request.method == 'POST' else None, instance=sample)
    if request.method == 'POST' and form.is_valid():
        sample = form.save()
        if had_result:
            assess_and_store(sample)
            messages.success(request, 'Sample updated and its assessment was refreshed.')
        else:
            messages.success(request, 'Sample updated.')
        return redirect('testing:sample_detail', sample_id=sample.pk)

    return render(
        request,
        'testing/sample_form.html',
        {'form': form, 'sample': sample, 'is_edit': True},
    )


@login_required
@require_http_methods(['GET', 'POST'])
def sample_delete(request: HttpRequest, sample_id: int) -> HttpResponse:
    """Ask for confirmation, then permanently delete an owned sample."""
    sample = _get_owned_sample(request, sample_id)
    if request.method == 'POST':
        name = sample.sample_name
        sample.delete()
        messages.success(request, f'Sample "{name}" was deleted.')
        return redirect('testing:sample_history')
    return render(request, 'testing/sample_confirm_delete.html', {'sample': sample})


@login_required
def sample_detail(request: HttpRequest, sample_id: int) -> HttpResponse:
    """Show a sample only to its owner."""
    sample = _get_owned_sample(request, sample_id)
    return render(request, 'testing/sample_detail.html', {'sample': sample})


@login_required
def sample_history(request: HttpRequest) -> HttpResponse:
    """List the farmer's samples with optional feed-type/status filters and paging."""
    samples = _owned_samples(request)

    feed_type = request.GET.get('feed_type', '')
    if feed_type in FeedSample.FeedType.values:
        samples = samples.filter(feed_type=feed_type)
    else:
        feed_type = ''

    status = request.GET.get('status', '')
    if status == UNASSESSED:
        samples = samples.filter(test_result__isnull=True)
    elif status in TestResult.Status.values:
        samples = samples.filter(test_result__quality_status=status)
    else:
        status = ''

    page = Paginator(samples, settings.SAMPLE_HISTORY_PAGE_SIZE).get_page(request.GET.get('page'))
    query = request.GET.copy()
    query.pop('page', None)
    context = {
        'samples': page,
        'feed_type_choices': FeedSample.FeedType.choices,
        'status_choices': [(UNASSESSED, 'Not assessed'), *TestResult.Status.choices],
        'selected_feed_type': feed_type,
        'selected_status': status,
        'filter_query': query.urlencode(),
        'is_filtered': bool(feed_type or status),
    }
    return render(request, 'testing/sample_history.html', context)


# CSV cells that start with these characters can be executed as formulas by
# spreadsheet software ("CSV injection"), so free-text values are neutralised.
_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def _csv_text(value: str) -> str:
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value


class _Echo:
    """File-like object whose ``write`` returns the value, for streaming CSV."""

    def write(self, value):
        return value


@login_required
def sample_export_csv(request: HttpRequest) -> StreamingHttpResponse:
    """Download all of the farmer's samples and assessments as a CSV file."""
    header = [
        'Sample',
        'Feed type',
        'Collection date',
        'pH',
        'Moisture %',
        'Temperature C',
        'Smell',
        'Visible mold',
        'Observations',
        'Status',
        'Score',
        'Assessed at',
    ]

    def rows():
        yield header
        for sample in _owned_samples(request).order_by('collection_date', 'pk').iterator():
            result = sample.result
            yield [
                _csv_text(sample.sample_name),
                sample.get_feed_type_display(),
                sample.collection_date.isoformat(),
                sample.ph_value,
                sample.moisture,
                sample.temperature,
                sample.get_smell_display(),
                'Yes' if sample.mold_present else 'No',
                _csv_text(sample.observations),
                result.quality_status if result else 'Not assessed',
                '' if result is None or result.quality_score is None else result.quality_score,
                result.tested_at.isoformat(timespec='seconds') if result else '',
            ]

    writer = csv.writer(_Echo())
    response = StreamingHttpResponse(
        (writer.writerow(row) for row in rows()),
        content_type='text/csv; charset=utf-8',
    )
    response['Content-Disposition'] = 'attachment; filename="nutrifarm-samples.csv"'
    return response


# --------------------------------------------------------------------------
# Assessment
# --------------------------------------------------------------------------


@login_required
@require_POST
def evaluate_sample(request: HttpRequest, sample_id: int) -> HttpResponse:
    """Evaluate one owned sample and create or update its single result."""
    sample = _get_owned_sample(request, sample_id)
    assess_and_store(sample)
    messages.success(request, 'The sample assessment has been saved.')
    return redirect('testing:sample_result', sample_id=sample.pk)


@login_required
def sample_result(request: HttpRequest, sample_id: int) -> HttpResponse:
    """Display an assessment only for a sample owned by the current farmer."""
    sample = _get_owned_sample(request, sample_id)
    return render(request, 'testing/sample_result.html', {'sample': sample, 'result': sample.result})
