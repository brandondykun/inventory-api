import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError

from apps.inventory.models import ParTemplate, ParTemplateItem
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
    ParTemplateItem.objects.create(template=tmpl, item=item, par_quantity=5, unit_of_measure=uom)
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
