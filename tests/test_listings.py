import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pydantic import ValidationError
from fastapi import HTTPException
from app.database import Base
from app.shemas import ListingCreate, ListingUpdate
from app.services.listing_service import create_listing, update_listing, search_listing, filter_listing, sort_listing, delete_listing, get_listing_by_id

class ListingsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create(self, title='Nike', description='Running shoes', price=100):
        return create_listing(ListingCreate(title=title, description=description, price=price, status='active'), self.db)

    def test_update_and_delete(self):
        item = self.create()
        item_id = item.id
        updated = update_listing(item_id, ListingUpdate(title='Adidas'), self.db)
        self.assertEqual(updated.title, 'Adidas')
        self.assertEqual(updated.price, 100)
        delete_listing(item_id, self.db)
        with self.assertRaises(HTTPException) as error:
            get_listing_by_id(item_id, self.db)
        self.assertEqual(error.exception.status_code, 404)

    def test_search_title_description_and_empty(self):
        first = self.create()
        second = self.create('Adidas', 'Rare Nike collaboration')
        self.assertEqual({x.id for x in search_listing('nike', self.db)}, {first.id, second.id})
        self.assertEqual(search_listing('absent', self.db), [])

    def test_filter_and_sort(self):
        self.create(price=100)
        self.create('Adidas', price=200)
        self.assertEqual(len(filter_listing('active', 150, 250, self.db)), 1)
        self.assertEqual([x.price for x in sort_listing(self.db, 'price', 'desc')], [200, 100])

    def test_validation(self):
        for changes in ({'price': 0}, {'price': -1}, {'price': float('nan')}, {'title': '   '}, {'status': 'invalid'}):
            values = dict(title='Nike', description='Shoes', price=100, status='active')
            values.update(changes)
            with self.assertRaises(ValidationError):
                ListingCreate(**values)
        with self.assertRaises(ValidationError):
            ListingUpdate(title=None)

if __name__ == '__main__':
    unittest.main()
