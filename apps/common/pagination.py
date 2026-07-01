"""Project-wide pagination."""

from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """Page-number pagination with a client-overridable, capped page size."""

    page_size_query_param = "page_size"
    max_page_size = 100
