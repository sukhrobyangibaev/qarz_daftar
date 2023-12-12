import pymongo

from models import Shop


def fill_shop(shop_cols: pymongo.collection.Collection):
    shop = Shop('Birnarsa Market', 'Urgench, Kh. Olimzhon street, 14', '+998991352729')
    shop_cols.insert_one(shop.to_dict())

# def fill_debtors(debtors_col: pymongo.collection.Collection):
# new test from yangibaevs
