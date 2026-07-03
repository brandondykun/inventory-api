# Inventory App — Slice 2b: Par Templates — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add par templates (`ParTemplate` + `ParTemplateItem` lines) to the inventory app, assignable to inventory units, with nested-read/sub-resource-write CRUD, an `is_active` soft-disable, cross-org validation, and clean 409 handling when deleting a catalog row a par line protects.

**Architecture:** New models in the existing `apps/inventory` app inheriting `BaseModel`. Reuse the `OrgScopedMixin`, the org app's `IsOrgMember`/`IsOrgAdmin` permission classes, and the existing serializer/view/url patterns from Slice 2a. Lines are a sub-resource of a template; the template detail serializer embeds lines read-only (so PATCH edits only the header). A new `Conflict` APIException (409) surfaces `ProtectedError` on the Item/UnitOfMeasure delete endpoints.

**Tech Stack:** Django, Django REST Framework, pytest + pytest-django, factory_boy, PostgreSQL, Docker Compose, ruff.

## Global Constraints

- All new models inherit `apps.common.models.BaseModel` (UUID pk, `created_at`, `updated_at`). Every model defines `Meta.ordering`.
- Everything is org-scoped. `ParTemplate` carries an `organization` FK; `ParTemplateItem` is org-scoped *through* its `template`. Every FK choice (`item`, `unit_of_measure`, a unit's `par_template`) is validated to the URL org in the serializer via `self.context["org_id"]`.
- Endpoints reuse `apps.inventory.views.OrgScopedMixin` and `apps.organizations.permissions.IsOrgMember` (read) / `IsOrgAdmin` (write). Reads = member, writes = admin.
- Errors flow through `apps.common.exceptions.api_exception_handler`, which wraps DRF errors as `{"error": {"status_code": N, "detail": <drf detail>}}`. **In tests, assert 400-body field keys at `resp.data["error"]["detail"]`; assert status codes directly for 403/404/409.**
- List endpoints paginate a `Meta.ordering`-ordered queryset (`resp.data["count"]`/`["results"]`).
- Tests run via `./scripts/test.sh <pytest args>` (Dockerized, `config.settings.test`). Migrations via `./scripts/manage.sh makemigrations inventory --name <name>`. Lint via `uv run ruff check apps/inventory && uv run ruff format apps/inventory`.
- **COMMIT POLICY (subagent execution):** implementers do NOT run `git add`/`git commit`. The "Commit" steps below describe the intended commit for the user; leave all app-code changes unstaged. (Spec/plan docs may be committed by the agent.)
- Creating an `Organization` in a test fires two `post_save` receivers (org: owner membership + free subscription; inventory: 4 default UnitTypes + 4 default UnitsOfMeasure). Scope all count assertions by `organization`. Par templates and lines are NOT seeded.

---

### Task 1: `ParTemplate` + `ParTemplateItem` models

**Files:**
- Modify: `apps/inventory/models.py` (add both models)
- Modify: `apps/inventory/tests/factories.py` (add `ParTemplateFactory`, `ParTemplateItemFactory`)
- Create: `apps/inventory/tests/test_par_templates.py`
- Create (generated): `apps/inventory/migrations/0004_partemplate_partemplateitem.py`

**Interfaces:**
- Produces `apps.inventory.models.ParTemplate(organization, name, description, is_active)` — `related_name="par_templates"`, `ordering=["name"]`.
- Produces `apps.inventory.models.ParTemplateItem(template, item, par_quantity, min_quantity, unit_of_measure)` — `template` CASCADE `related_name="lines"`, `item` PROTECT `related_name="par_lines"`, `unit_of_measure` PROTECT `related_name="par_lines"`, `unique_together=("template","item")`, `ordering=["item__name"]`.
- Produces `ParTemplateFactory`, `ParTemplateItemFactory`.

- [ ] **Step 1: Write the failing model tests**

`apps/inventory/tests/test_par_templates.py`:

```python
import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError

from apps.inventory.models import Item, ParTemplate, ParTemplateItem, UnitOfMeasure
from apps.inventory.tests.factories import (
    ItemFactory,
    ParTemplateFactory,
    ParTemplateItemFactory,
    UnitOfMeasureFactory,
)
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_par_template_defaults_and_str():
    tmpl = ParTemplate.objects.create(organization=OrganizationFactory(), name="Rig A")
    assert tmpl.is_active is True
    assert str(tmpl) == "Rig A"


@pytest.mark.django_db
def test_line_unique_per_template_and_item():
    tmpl = ParTemplateFactory()
    item = ItemFactory(organization=tmpl.organization)
    uom = UnitOfMeasureFactory(organization=tmpl.organization)
    ParTemplateItem.objects.create(
        template=tmpl, item=item, par_quantity=5, unit_of_measure=uom
    )
    with pytest.raises(IntegrityError):
        ParTemplateItem.objects.create(
            template=tmpl, item=item, par_quantity=3, unit_of_measure=uom
        )


@pytest.mark.django_db
def test_deleting_template_cascades_lines():
    line = ParTemplateItemFactory()
    tmpl = line.template
    tmpl.delete()
    assert ParTemplateItem.objects.filter(pk=line.pk).count() == 0


@pytest.mark.django_db
def test_item_referenced_by_line_is_protected():
    line = ParTemplateItemFactory()
    with pytest.raises(ProtectedError):
        line.item.delete()


@pytest.mark.django_db
def test_unit_of_measure_referenced_by_line_is_protected():
    line = ParTemplateItemFactory()
    with pytest.raises(ProtectedError):
        line.unit_of_measure.delete()
```

- [ ] **Step 2: Run to verify failure**

Run: `./scripts/test.sh apps/inventory/tests/test_par_templates.py -v`
Expected: FAIL with `ImportError: cannot import name 'ParTemplate'`.

- [ ] **Step 3: Add the models**

Append to `apps/inventory/models.py`:

```python
class ParTemplate(BaseModel):
    """The ideal set of items and counts for a unit (the "should-be"). Owned by
    the org and assignable to many units (e.g. a whole fleet)."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="par_templates"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ParTemplateItem(BaseModel):
    """One line of a par template: an item and its target quantity."""

    template = models.ForeignKey(
        ParTemplate, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="par_lines")
    par_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    min_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    unit_of_measure = models.ForeignKey(
        UnitOfMeasure, on_delete=models.PROTECT, related_name="par_lines"
    )

    class Meta:
        unique_together = ("template", "item")
        ordering = ["item__name"]

    def __str__(self):
        return f"{self.item}: {self.par_quantity} {self.unit_of_measure}"
```

- [ ] **Step 4: Add factories**

Append to `apps/inventory/tests/factories.py` (extend the model import line to include `ParTemplate, ParTemplateItem`):

```python
from apps.inventory.models import (  # replace the existing inventory model import
    InventoryUnit,
    Item,
    ParTemplate,
    ParTemplateItem,
    UnitOfMeasure,
    UnitType,
)


class ParTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ParTemplate

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Par Template {n}")


class ParTemplateItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ParTemplateItem

    template = factory.SubFactory(ParTemplateFactory)
    item = factory.SubFactory(
        ItemFactory, organization=factory.SelfAttribute("..template.organization")
    )
    unit_of_measure = factory.SubFactory(
        UnitOfMeasureFactory,
        organization=factory.SelfAttribute("..template.organization"),
    )
    par_quantity = 5
```

- [ ] **Step 5: Generate the migration**

Run: `./scripts/manage.sh makemigrations inventory --name partemplate_partemplateitem`
Expected: creates `apps/inventory/migrations/0004_partemplate_partemplateitem.py`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_par_templates.py -v`
Expected: 5 passed.

- [ ] **Step 7: Lint + prepare commit**

Run: `uv run ruff check apps/inventory && uv run ruff format apps/inventory`

Intended commit:

```bash
git add apps/inventory
git commit -m "feat: add ParTemplate and ParTemplateItem models"
```

---

### Task 2: ParTemplate CRUD API (header + nested-read lines)

**Files:**
- Modify: `apps/inventory/serializers.py` (add `ParTemplateItemSerializer` [read fields], `ParTemplateSerializer`, `ParTemplateDetailSerializer`)
- Modify: `apps/inventory/views.py` (add `ParTemplateListCreateView`, `ParTemplateDetailView`)
- Modify: `apps/inventory/urls.py` (add template routes)
- Create: `apps/inventory/tests/test_par_templates_api.py`

**Interfaces:**
- Consumes `OrgScopedMixin`, `ParTemplate`/`ParTemplateItem` (Task 1).
- Produces `ParTemplateItemSerializer` (fields: `id`, `item`, `par_quantity`, `min_quantity`, `unit_of_measure`, `created_at`, `updated_at`; validation added in Task 3), `ParTemplateSerializer` (header), `ParTemplateDetailSerializer` (header + `lines` read-only). Routes: `/api/organizations/{org_id}/par-templates/` and `/{id}/`.

- [ ] **Step 1: Write the failing API tests**

`apps/inventory/tests/test_par_templates_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.inventory.models import ParTemplate
from apps.inventory.tests.factories import ParTemplateFactory, ParTemplateItemFactory
from apps.organizations.models import Membership
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


def list_url(org):
    return f"/api/organizations/{org.id}/par-templates/"


def detail_url(org, tmpl):
    return f"/api/organizations/{org.id}/par-templates/{tmpl.id}/"


@pytest.mark.django_db
def test_admin_creates_template(client_for):
    org = OrganizationFactory()
    resp = client_for(org.owner).post(list_url(org), {"name": "Rig A"})
    assert resp.status_code == 201
    assert ParTemplate.objects.filter(organization=org, name="Rig A").exists()


@pytest.mark.django_db
def test_list_defaults_to_active_only(client_for):
    org = OrganizationFactory()
    ParTemplateFactory(organization=org, name="Active", is_active=True)
    ParTemplateFactory(organization=org, name="Retired", is_active=False)
    resp = client_for(org.owner).get(list_url(org))
    assert resp.status_code == 200
    names = [row["name"] for row in resp.data["results"]]
    assert names == ["Active"]


@pytest.mark.django_db
def test_list_is_active_false_and_all(client_for):
    org = OrganizationFactory()
    ParTemplateFactory(organization=org, name="Active", is_active=True)
    ParTemplateFactory(organization=org, name="Retired", is_active=False)
    inactive = client_for(org.owner).get(list_url(org) + "?is_active=false")
    assert [r["name"] for r in inactive.data["results"]] == ["Retired"]
    allrows = client_for(org.owner).get(list_url(org) + "?is_active=all")
    assert allrows.data["count"] == 2


@pytest.mark.django_db
def test_detail_includes_nested_lines(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    ParTemplateItemFactory(template=tmpl)
    resp = client_for(org.owner).get(detail_url(org, tmpl))
    assert resp.status_code == 200
    assert len(resp.data["lines"]) == 1
    assert "par_quantity" in resp.data["lines"][0]


@pytest.mark.django_db
def test_patch_edits_header_ignores_lines(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org, name="Old")
    resp = client_for(org.owner).patch(
        detail_url(org, tmpl), {"name": "New", "lines": []}, format="json"
    )
    assert resp.status_code == 200
    tmpl.refresh_from_db()
    assert tmpl.name == "New"


@pytest.mark.django_db
def test_member_reads_admin_writes(client_for):
    org = OrganizationFactory()
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    assert client_for(member).get(list_url(org)).status_code == 200
    assert client_for(member).post(list_url(org), {"name": "X"}).status_code == 403


@pytest.mark.django_db
def test_non_member_and_cross_org(client_for):
    org = OrganizationFactory()
    other = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=other)
    assert client_for(UserFactory()).get(list_url(org)).status_code == 403
    # org.owner is not a member of `other`, requesting other's template under other's org
    assert client_for(org.owner).get(detail_url(other, tmpl)).status_code == 403
```

- [ ] **Step 2: Run to verify failure**

Run: `./scripts/test.sh apps/inventory/tests/test_par_templates_api.py -v`
Expected: FAIL — routes 404 / serializers not defined.

- [ ] **Step 3: Add the serializers**

Append to `apps/inventory/serializers.py` (extend the model import to include `ParTemplate, ParTemplateItem`):

```python
class ParTemplateItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParTemplateItem
        fields = [
            "id",
            "item",
            "par_quantity",
            "min_quantity",
            "unit_of_measure",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    # Write validation (cross-org, quantity rules, duplicate) is added in Task 3.


class ParTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParTemplate
        fields = ["id", "name", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ParTemplateDetailSerializer(ParTemplateSerializer):
    lines = ParTemplateItemSerializer(many=True, read_only=True)

    class Meta(ParTemplateSerializer.Meta):
        fields = ParTemplateSerializer.Meta.fields + ["lines"]
```

- [ ] **Step 4: Add the views**

In `apps/inventory/views.py`, extend the model import with `ParTemplate` and the serializer import with `ParTemplateDetailSerializer, ParTemplateSerializer`, then append:

```python
class ParTemplateListCreateView(OrgScopedMixin, generics.ListCreateAPIView):
    serializer_class = ParTemplateSerializer

    def get_queryset(self):
        qs = ParTemplate.objects.filter(organization_id=self.get_org_id())
        is_active = self.request.query_params.get("is_active")
        if is_active is None:
            return qs.filter(is_active=True)
        if is_active.lower() == "all":
            return qs
        return qs.filter(is_active=is_active.lower() == "true")


class ParTemplateDetailView(OrgScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ParTemplateDetailSerializer

    def get_queryset(self):
        return ParTemplate.objects.filter(organization_id=self.get_org_id())
```

- [ ] **Step 5: Add the routes**

Add to `apps/inventory/urls.py` (import the two views, add to `urlpatterns`):

```python
    path(
        "organizations/<uuid:org_id>/par-templates/",
        ParTemplateListCreateView.as_view(),
        name="par-template-list-create",
    ),
    path(
        "organizations/<uuid:org_id>/par-templates/<uuid:pk>/",
        ParTemplateDetailView.as_view(),
        name="par-template-detail",
    ),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_par_templates_api.py -v`
Expected: 7 passed.

- [ ] **Step 7: Lint + prepare commit**

Run: `uv run ruff check apps/inventory && uv run ruff format apps/inventory`

Intended commit:

```bash
git add apps/inventory
git commit -m "feat: add ParTemplate CRUD API with nested-read lines and is_active filter"
```

---

### Task 3: Par template line CRUD (sub-resource) with validation

**Files:**
- Modify: `apps/inventory/serializers.py` (add validation to `ParTemplateItemSerializer`)
- Modify: `apps/inventory/views.py` (add `ParTemplateLineListCreateView`, `ParTemplateLineDetailView`)
- Modify: `apps/inventory/urls.py` (add line routes)
- Create: `apps/inventory/tests/test_par_lines_api.py`

**Interfaces:**
- Consumes `ParTemplateItemSerializer` (Task 2), `OrgScopedMixin`.
- Produces line endpoints under `/api/organizations/{org_id}/par-templates/{template_id}/lines/` and `/{pk}/`. The serializer gains `validate_item`, `validate_unit_of_measure` (cross-org via `context["org_id"]`), and `validate` (quantity rules + duplicate via `context["template_id"]`).

- [ ] **Step 1: Write the failing tests**

`apps/inventory/tests/test_par_lines_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.inventory.models import ParTemplateItem
from apps.inventory.tests.factories import (
    ItemFactory,
    ParTemplateFactory,
    ParTemplateItemFactory,
    UnitOfMeasureFactory,
)
from apps.organizations.tests.factories import OrganizationFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


def lines_url(org, tmpl):
    return f"/api/organizations/{org.id}/par-templates/{tmpl.id}/lines/"


@pytest.mark.django_db
def test_add_line(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    item = ItemFactory(organization=org)
    uom = UnitOfMeasureFactory(organization=org)
    resp = client_for(org.owner).post(
        lines_url(org, tmpl),
        {"item": str(item.id), "par_quantity": "5.00", "unit_of_measure": str(uom.id)},
    )
    assert resp.status_code == 201
    assert ParTemplateItem.objects.filter(template=tmpl, item=item).exists()


@pytest.mark.django_db
def test_cross_org_item_rejected(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    foreign_item = ItemFactory(organization=OrganizationFactory())
    uom = UnitOfMeasureFactory(organization=org)
    resp = client_for(org.owner).post(
        lines_url(org, tmpl),
        {"item": str(foreign_item.id), "par_quantity": "1", "unit_of_measure": str(uom.id)},
    )
    assert resp.status_code == 400
    assert "item" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_cross_org_uom_rejected(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    item = ItemFactory(organization=org)
    foreign_uom = UnitOfMeasureFactory(organization=OrganizationFactory())
    resp = client_for(org.owner).post(
        lines_url(org, tmpl),
        {"item": str(item.id), "par_quantity": "1", "unit_of_measure": str(foreign_uom.id)},
    )
    assert resp.status_code == 400
    assert "unit_of_measure" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_negative_par_and_min_gt_par_rejected(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    item = ItemFactory(organization=org)
    uom = UnitOfMeasureFactory(organization=org)
    neg = client_for(org.owner).post(
        lines_url(org, tmpl),
        {"item": str(item.id), "par_quantity": "-1", "unit_of_measure": str(uom.id)},
    )
    assert neg.status_code == 400
    assert "par_quantity" in neg.data["error"]["detail"]
    bad_min = client_for(org.owner).post(
        lines_url(org, tmpl),
        {
            "item": str(item.id),
            "par_quantity": "5",
            "min_quantity": "9",
            "unit_of_measure": str(uom.id),
        },
    )
    assert bad_min.status_code == 400
    assert "min_quantity" in bad_min.data["error"]["detail"]


@pytest.mark.django_db
def test_duplicate_line_rejected(client_for):
    org = OrganizationFactory()
    line = ParTemplateItemFactory(template=ParTemplateFactory(organization=org))
    resp = client_for(org.owner).post(
        lines_url(org, line.template),
        {
            "item": str(line.item.id),
            "par_quantity": "3",
            "unit_of_measure": str(line.unit_of_measure.id),
        },
    )
    assert resp.status_code == 400
    assert "item" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_lines_scoped_to_template_and_org(client_for):
    org = OrganizationFactory()
    other = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    ParTemplateItemFactory(template=tmpl)
    # A template belonging to another org is not reachable under this org.
    foreign_tmpl = ParTemplateFactory(organization=other)
    resp = client_for(org.owner).get(lines_url(org, foreign_tmpl))
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `./scripts/test.sh apps/inventory/tests/test_par_lines_api.py -v`
Expected: FAIL — line routes 404.

- [ ] **Step 3: Add validation to `ParTemplateItemSerializer`**

In `apps/inventory/serializers.py`, replace the `# Write validation ...` comment in `ParTemplateItemSerializer` with these methods (add `from .models import ParTemplateItem` usage — it is already imported):

```python
    def validate_item(self, value):
        if str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError("Item must belong to this organization.")
        return value

    def validate_unit_of_measure(self, value):
        if str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError(
                "Unit of measure must belong to this organization."
            )
        return value

    def validate(self, attrs):
        par = attrs.get("par_quantity", getattr(self.instance, "par_quantity", None))
        min_q = attrs.get("min_quantity", getattr(self.instance, "min_quantity", None))
        if par is not None and par < 0:
            raise serializers.ValidationError(
                {"par_quantity": "Must be zero or greater."}
            )
        if par is not None and min_q is not None and min_q > par:
            raise serializers.ValidationError(
                {"min_quantity": "Cannot exceed par_quantity."}
            )
        # Duplicate (template, item) — template comes from the URL, not the body.
        item = attrs.get("item", getattr(self.instance, "item", None))
        template_id = self.context.get("template_id")
        if item is not None and template_id is not None:
            qs = ParTemplateItem.objects.filter(template_id=template_id, item=item)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"item": "This item is already on the template."}
                )
        return attrs
```

- [ ] **Step 4: Add the line views**

In `apps/inventory/views.py`, add `get_object_or_404` import (`from django.shortcuts import get_object_or_404`), extend the model import with `ParTemplate, ParTemplateItem` and the serializer import with `ParTemplateItemSerializer`, then append:

```python
class _TemplateScopedMixin(OrgScopedMixin):
    """Line endpoints: scope to one template that must belong to the URL org."""

    serializer_class = ParTemplateItemSerializer

    def get_template(self):
        return get_object_or_404(
            ParTemplate,
            pk=self.kwargs["template_id"],
            organization_id=self.get_org_id(),
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["template_id"] = self.kwargs["template_id"]
        return ctx


class ParTemplateLineListCreateView(_TemplateScopedMixin, generics.ListCreateAPIView):
    def get_queryset(self):
        return ParTemplateItem.objects.filter(template=self.get_template())

    def perform_create(self, serializer):
        serializer.save(template=self.get_template())


class ParTemplateLineDetailView(
    _TemplateScopedMixin, generics.RetrieveUpdateDestroyAPIView
):
    def get_queryset(self):
        return ParTemplateItem.objects.filter(
            template_id=self.kwargs["template_id"],
            template__organization_id=self.get_org_id(),
        )
```

- [ ] **Step 5: Add the line routes**

Add to `apps/inventory/urls.py` (import the two views):

```python
    path(
        "organizations/<uuid:org_id>/par-templates/<uuid:template_id>/lines/",
        ParTemplateLineListCreateView.as_view(),
        name="par-line-list-create",
    ),
    path(
        "organizations/<uuid:org_id>/par-templates/<uuid:template_id>/lines/<uuid:pk>/",
        ParTemplateLineDetailView.as_view(),
        name="par-line-detail",
    ),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_par_lines_api.py -v`
Expected: 6 passed.

- [ ] **Step 7: Lint + prepare commit**

Run: `uv run ruff check apps/inventory && uv run ruff format apps/inventory`

Intended commit:

```bash
git add apps/inventory
git commit -m "feat: add par template line CRUD with cross-org and quantity validation"
```

---

### Task 4: Assign `par_template` to inventory units

**Files:**
- Modify: `apps/inventory/models.py` (add `InventoryUnit.par_template`)
- Modify: `apps/inventory/serializers.py` (`InventoryUnitSerializer`: add field + `validate_par_template`)
- Create (generated): `apps/inventory/migrations/0005_inventoryunit_par_template.py`
- Create: `apps/inventory/tests/test_unit_par_assignment.py`

**Interfaces:**
- Consumes `ParTemplate` (Task 1), `InventoryUnitSerializer` (2a).
- Produces `InventoryUnit.par_template` (FK → ParTemplate, `null=True`, `blank=True`, `SET_NULL`, `related_name="units"`), exposed and validated on the existing unit endpoints.

- [ ] **Step 1: Write the failing tests**

`apps/inventory/tests/test_unit_par_assignment.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.inventory.models import InventoryUnit
from apps.inventory.tests.factories import InventoryUnitFactory, ParTemplateFactory
from apps.organizations.tests.factories import OrganizationFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


def unit_detail(org, unit):
    return f"/api/organizations/{org.id}/units/{unit.id}/"


@pytest.mark.django_db
def test_assign_and_clear_par_template(client_for):
    org = OrganizationFactory()
    unit = InventoryUnitFactory(organization=org)
    tmpl = ParTemplateFactory(organization=org)
    assign = client_for(org.owner).patch(
        unit_detail(org, unit), {"par_template": str(tmpl.id)}
    )
    assert assign.status_code == 200
    unit.refresh_from_db()
    assert unit.par_template_id == tmpl.id
    clear = client_for(org.owner).patch(
        unit_detail(org, unit), {"par_template": None}, format="json"
    )
    assert clear.status_code == 200
    unit.refresh_from_db()
    assert unit.par_template_id is None


@pytest.mark.django_db
def test_cannot_assign_inactive_template(client_for):
    org = OrganizationFactory()
    unit = InventoryUnitFactory(organization=org)
    inactive = ParTemplateFactory(organization=org, is_active=False)
    resp = client_for(org.owner).patch(
        unit_detail(org, unit), {"par_template": str(inactive.id)}
    )
    assert resp.status_code == 400
    assert "par_template" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_cannot_assign_other_orgs_template(client_for):
    org = OrganizationFactory()
    unit = InventoryUnitFactory(organization=org)
    foreign = ParTemplateFactory(organization=OrganizationFactory())
    resp = client_for(org.owner).patch(
        unit_detail(org, unit), {"par_template": str(foreign.id)}
    )
    assert resp.status_code == 400
    assert "par_template" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_deleting_template_detaches_unit(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    unit = InventoryUnitFactory(organization=org, par_template=tmpl)
    tmpl.delete()
    unit.refresh_from_db()
    assert unit.par_template_id is None
```

- [ ] **Step 2: Run to verify failure**

Run: `./scripts/test.sh apps/inventory/tests/test_unit_par_assignment.py -v`
Expected: FAIL — `par_template` is not a field / not accepted.

- [ ] **Step 3: Add the model field**

In `apps/inventory/models.py`, inside `class InventoryUnit`, add after the `parent` field:

```python
    par_template = models.ForeignKey(
        "ParTemplate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="units",
    )
```

(Use the string reference `"ParTemplate"` since `ParTemplate` is defined later in the file.)

- [ ] **Step 4: Generate the migration**

Run: `./scripts/manage.sh makemigrations inventory --name inventoryunit_par_template`
Expected: creates `apps/inventory/migrations/0005_inventoryunit_par_template.py` (a single `AddField`).

- [ ] **Step 5: Add the field to the serializer + validation**

In `apps/inventory/serializers.py`, add `"par_template"` to `InventoryUnitSerializer.Meta.fields` (after `"parent"`), and add this method to `InventoryUnitSerializer`:

```python
    def validate_par_template(self, value):
        if value is None:
            return value
        if str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError(
                "Par template must belong to this organization."
            )
        if not value.is_active:
            raise serializers.ValidationError("Cannot assign an inactive par template.")
        return value
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_unit_par_assignment.py -v`
Expected: 4 passed.

- [ ] **Step 7: Lint + prepare commit**

Run: `uv run ruff check apps/inventory && uv run ruff format apps/inventory`

Intended commit:

```bash
git add apps/inventory
git commit -m "feat: allow assigning an active par template to an inventory unit"
```

---

### Task 5: `ProtectedError` → 409 on Item / UnitOfMeasure delete

**Files:**
- Create: `apps/inventory/exceptions.py` (`Conflict`)
- Modify: `apps/inventory/views.py` (`ProtectedDeleteMixin`; apply to `ItemDetailView`, `UnitOfMeasureDetailView`)
- Create: `apps/inventory/tests/test_protected_delete.py`

**Interfaces:**
- Produces `apps.inventory.exceptions.Conflict` (APIException, `status_code=409`) and `ProtectedDeleteMixin` (overrides `perform_destroy` to map `django.db.models.ProtectedError` → `Conflict`).

- [ ] **Step 1: Write the failing tests**

`apps/inventory/tests/test_protected_delete.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.inventory.models import Item, UnitOfMeasure
from apps.inventory.tests.factories import (
    ItemFactory,
    ParTemplateItemFactory,
    UnitOfMeasureFactory,
)
from apps.organizations.tests.factories import OrganizationFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


@pytest.mark.django_db
def test_delete_item_referenced_by_par_line_returns_409(client_for):
    org = OrganizationFactory()
    line = ParTemplateItemFactory(
        template__organization=org,
        item=ItemFactory(organization=org),
        unit_of_measure=UnitOfMeasureFactory(organization=org),
    )
    url = f"/api/organizations/{org.id}/items/{line.item.id}/"
    resp = client_for(org.owner).delete(url)
    assert resp.status_code == 409
    assert Item.objects.filter(pk=line.item.id).exists()


@pytest.mark.django_db
def test_delete_uom_referenced_by_par_line_returns_409(client_for):
    org = OrganizationFactory()
    line = ParTemplateItemFactory(
        template__organization=org,
        item=ItemFactory(organization=org),
        unit_of_measure=UnitOfMeasureFactory(organization=org),
    )
    url = f"/api/organizations/{org.id}/units-of-measure/{line.unit_of_measure.id}/"
    resp = client_for(org.owner).delete(url)
    assert resp.status_code == 409
    assert UnitOfMeasure.objects.filter(pk=line.unit_of_measure.id).exists()


@pytest.mark.django_db
def test_delete_unreferenced_item_still_204(client_for):
    org = OrganizationFactory()
    item = ItemFactory(organization=org)
    url = f"/api/organizations/{org.id}/items/{item.id}/"
    resp = client_for(org.owner).delete(url)
    assert resp.status_code == 204
    assert not Item.objects.filter(pk=item.id).exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `./scripts/test.sh apps/inventory/tests/test_protected_delete.py -v`
Expected: FAIL — the two referenced-delete cases raise `ProtectedError` (500), not 409.

- [ ] **Step 3: Add the `Conflict` exception**

`apps/inventory/exceptions.py`:

```python
"""Custom API exceptions for the inventory app."""

from rest_framework.exceptions import APIException


class Conflict(APIException):
    status_code = 409
    default_detail = "This record is referenced by other records and cannot be deleted."
    default_code = "conflict"
```

- [ ] **Step 4: Add the mixin and apply it**

In `apps/inventory/views.py`, add imports:

```python
from django.db.models import ProtectedError

from .exceptions import Conflict
```

Add the mixin (near `OrgScopedMixin`):

```python
class ProtectedDeleteMixin:
    """Turn a DB-level ProtectedError on delete into a clean 409 instead of a
    500. Used where a catalog row may be referenced by PROTECT foreign keys
    (e.g. par template lines)."""

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError as exc:
            raise Conflict(
                "Cannot delete: this record is still referenced by other records "
                "(e.g. par template lines). Remove those references first."
            ) from exc
```

Change the two detail-view class declarations to mix it in FIRST (so its `perform_destroy` wins):

```python
class UnitOfMeasureDetailView(
    ProtectedDeleteMixin, OrgScopedMixin, generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = UnitOfMeasureSerializer

    def get_queryset(self):
        return UnitOfMeasure.objects.filter(organization_id=self.get_org_id())
```

```python
class ItemDetailView(
    ProtectedDeleteMixin, OrgScopedMixin, generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = ItemSerializer

    def get_queryset(self):
        return Item.objects.filter(organization_id=self.get_org_id())
```

- [ ] **Step 4b: Run to verify it passes**

Run: `./scripts/test.sh apps/inventory/tests/test_protected_delete.py -v`
Expected: 3 passed.

- [ ] **Step 5: Regression — the 2a Item/UoM tests still pass**

Run: `./scripts/test.sh apps/inventory/tests/test_items_api.py apps/inventory/tests/test_catalog_api.py -v`
Expected: all pass (the mixin only changes the delete path on a `ProtectedError`).

- [ ] **Step 6: Lint + prepare commit**

Run: `uv run ruff check apps/inventory && uv run ruff format apps/inventory`

Intended commit:

```bash
git add apps/inventory
git commit -m "feat: return 409 when deleting a catalog row protected by a par line"
```

---

### Task 6: Admin registration + full-suite verification

**Files:**
- Modify: `apps/inventory/admin.py` (register `ParTemplate` with a `ParTemplateItem` inline)

**Interfaces:**
- Consumes `ParTemplate`, `ParTemplateItem`.

- [ ] **Step 1: Register in admin**

Append to `apps/inventory/admin.py` (extend the model import with `ParTemplate, ParTemplateItem`):

```python
class ParTemplateItemInline(admin.TabularInline):
    model = ParTemplateItem
    extra = 0
    raw_id_fields = ["item", "unit_of_measure"]


@admin.register(ParTemplate)
class ParTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "is_active"]
    list_filter = ["organization", "is_active"]
    search_fields = ["name"]
    inlines = [ParTemplateItemInline]
```

- [ ] **Step 2: Run the full project suite**

Run: `./scripts/test.sh`
Expected: the entire suite passes (all prior tests + the new par-template tests), 0 failures, 0 warnings.

- [ ] **Step 3: Lint the touched surface**

Run: `uv run ruff check apps/inventory && uv run ruff format apps/inventory`
Expected: no issues.

- [ ] **Step 4: Update the SDD progress ledger**

Update `.superpowers/sdd/progress.md` with Slice 2b completion (tasks, test counts, files), following the existing format.

- [ ] **Step 5: Prepare commit**

Intended commit:

```bash
git add apps/inventory .superpowers/sdd/progress.md
git commit -m "feat: register par templates in Django admin"
```

---

## Self-Review

**Spec coverage** (each spec section → task):
- `ParTemplate`, `ParTemplateItem` models (fields, PROTECT/CASCADE, unique_together, ordering) → Task 1.
- `InventoryUnit.par_template` FK + migration → Task 4.
- Nested-read / sub-resource-write API → Task 2 (template header + nested read) + Task 3 (line CRUD).
- `is_active` soft-disable: default-active list + `?is_active=false|all` → Task 2; assign-inactive→400 → Task 4.
- Cross-org validation: line item/uom → Task 3; unit par_template → Task 4.
- Quantity rules (`par ≥ 0`, `min ≤ par`) → Task 3.
- Duplicate `(template,item)` → 400 → Task 3.
- `PROTECT` → 409 on Item/UoM delete → Task 5.
- Permissions / cross-org 403/404 → Tasks 2, 3.
- Admin → Task 6.

**Placeholder scan:** No TBD/TODO; every step has concrete code or an exact command. The Task 2 note "validation added in Task 3" is a real forward-reference the interface block documents, not a deferred placeholder — the serializer is functional (read-only nested use) without it.

**Type consistency:** `OrgScopedMixin`, `get_org_id()`, `context["org_id"]`, `context["template_id"]`, `ParTemplateItemSerializer`, `ParTemplateDetailSerializer`, `_TemplateScopedMixin`, `ProtectedDeleteMixin`, `Conflict`, and `related_name`s (`par_templates`, `lines`, `par_lines`, `units`) are named identically across tasks. Migration numbering (`0004` models, `0005` FK) is sequential from the existing `0003_inventoryunit`.

**One deliberate design note:** `ParTemplateItemSerializer` cross-org checks read `self.context["org_id"]`, set by `OrgScopedMixin.get_serializer_context`; the duplicate check reads `self.context["template_id"]`, set by `_TemplateScopedMixin`. Both contexts are guaranteed present on the line endpoints, which is the only place the serializer is used for writes (its use inside `ParTemplateDetailSerializer` is read-only, so the validators never run there).
