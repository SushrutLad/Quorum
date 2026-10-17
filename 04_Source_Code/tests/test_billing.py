"""Unit tests for the slab billing calculation (billing.calculate_bill)."""
import pytest

from billing import calculate_bill

ELECTRICITY = [(0, 100, 3.50), (100, 300, 5.00), (300, None, 7.00)]
WATER = [(0, 10, 8.00), (10, 20, 12.00), (20, None, 18.00)]


def test_ut01_two_slabs():
    # 100 x 3.50 + 150 x 5.00 = 1100; + 50 fixed = 1150; + 5% = 1207.50
    bill = calculate_bill(250, ELECTRICITY, 50, 5)
    assert bill["energy_charge"] == 1100.00
    assert bill["tax_amount"] == 57.50
    assert bill["total_amount"] == 1207.50
    assert len(bill["items"]) == 2


def test_ut02_zero_units_only_fixed_charge():
    bill = calculate_bill(0, ELECTRICITY, 50, 5)
    assert bill["energy_charge"] == 0
    assert bill["total_amount"] == 52.50
    assert bill["items"] == []


def test_ut03_exact_slab_boundary():
    bill = calculate_bill(100, ELECTRICITY, 50, 5)
    assert bill["energy_charge"] == 350.00
    assert len(bill["items"]) == 1
    assert bill["total_amount"] == 420.00


def test_ut04_open_ended_top_slab():
    # 350 + 200 x 5 + 100 x 7 = 2050; + 50 = 2100; + 5% = 2205
    bill = calculate_bill(400, ELECTRICITY, 50, 5)
    assert bill["energy_charge"] == 2050.00
    assert bill["total_amount"] == 2205.00
    assert bill["items"][-1]["units"] == 100


def test_ut05_negative_units_rejected():
    with pytest.raises(ValueError):
        calculate_bill(-5, ELECTRICITY, 50, 5)


def test_ut06_water_without_tax_and_decimal_units():
    # 10 x 8 + 5.5 x 12 = 146; + 40 fixed = 186; no tax
    bill = calculate_bill(15.5, WATER, 40, 0)
    assert bill["energy_charge"] == 146.00
    assert bill["tax_amount"] == 0
    assert bill["total_amount"] == 186.00
