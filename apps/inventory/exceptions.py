"""Custom API exceptions for the inventory app."""

from rest_framework.exceptions import APIException


class Conflict(APIException):
    status_code = 409
    default_detail = "This record is referenced by other records and cannot be deleted."
    default_code = "conflict"
