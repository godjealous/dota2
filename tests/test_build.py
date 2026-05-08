import json
from scripts.build import merge_heroes, merge_items


def test_merge_heroes_has_required_fields():
    heroes = merge_heroes()
    assert len(heroes) > 100

    hero = heroes.get("npc_dota_hero_antimage")
    assert hero is not None
    assert "id" in hero
    assert "name" in hero
    assert "name_en" in hero
    assert "primary_attr" in hero
    assert "abilities" in hero
    assert len(hero["abilities"]) > 0

    ability = hero["abilities"][0]
    assert "key" in ability
    assert "name" in ability


def test_merge_items_has_required_fields():
    items = merge_items()
    assert len(items) > 100

    item = items.get("item_blink")
    assert item is not None
    assert "id" in item
    assert "name" in item
    assert "name_en" in item
    assert "cost" in item
