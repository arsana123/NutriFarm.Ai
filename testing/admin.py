from django.contrib import admin

from .models import ContactMessage, FeedSample, TestResult


class TestResultInline(admin.StackedInline):
    __test__ = False  # not a test case
    model = TestResult
    extra = 0
    can_delete = False
    readonly_fields = (
        'quality_score',
        'quality_status',
        'assessment_explanation',
        'recommendations',
        'findings',
        'tested_at',
    )


@admin.register(FeedSample)
class FeedSampleAdmin(admin.ModelAdmin):
    list_display = (
        'sample_name',
        'farmer',
        'feed_type',
        'collection_date',
        'created_at',
        'mold_present',
    )
    list_filter = ('feed_type', 'mold_present', 'created_at')
    list_select_related = ('farmer',)
    search_fields = ('sample_name', 'farmer__username', 'farmer__email')
    readonly_fields = ('created_at',)
    date_hierarchy = 'collection_date'
    inlines = [TestResultInline]


@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    __test__ = False  # not a test case
    list_display = ('sample', 'quality_score', 'quality_status', 'tested_at')
    list_filter = ('quality_status', 'tested_at')
    list_select_related = ('sample',)
    search_fields = ('sample__sample_name', 'sample__farmer__username')
    readonly_fields = ('tested_at',)


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'created_at', 'is_handled')
    list_filter = ('is_handled', 'created_at')
    list_editable = ('is_handled',)
    search_fields = ('name', 'email', 'message')
    readonly_fields = ('name', 'email', 'message', 'created_at')
