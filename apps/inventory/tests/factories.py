"""Test factories for the inventory app."""

import factory

from apps.inventory.models import (
    InventoryUnit,
    Item,
    ParTemplate,
    ParTemplateItem,
    UnitOfMeasure,
    UnitType,
)
from apps.organizations.tests.factories import OrganizationFactory


class UnitTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UnitType

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Unit Type {n}")


class UnitOfMeasureFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UnitOfMeasure

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Unit {n}")
    abbreviation = "ea"


class ItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Item

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Item {n}")


class InventoryUnitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InventoryUnit

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Unit {n}")


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
