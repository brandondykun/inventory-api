"""Test factories for the inventory app."""

import factory

from apps.inventory.models import InventoryUnit, Item, UnitOfMeasure, UnitType
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
