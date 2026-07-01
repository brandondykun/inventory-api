"""Email-based user admin, themed with django-unfold."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm as UnfoldAdminPasswordChangeForm
from unfold.forms import UserChangeForm, UserCreationForm

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin, ModelAdmin):
    """User admin adapted for an email identifier (no username field)."""

    # Unfold-styled forms.
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = UnfoldAdminPasswordChangeForm

    ordering = ["-created_at"]
    list_display = ["email", "first_name", "last_name", "is_staff", "is_active"]
    list_filter = ["is_staff", "is_superuser", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    readonly_fields = ["last_login", "created_at", "updated_at"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
