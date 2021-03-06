# This file should connect to postgres and begin the dump from GDAX's 
# WebsocketClient stream. This custom implementation is required in
# order to put each record into postgres.
#
# Author: @drewrice2

from __future__ import print_function
import gdax
import json
import base64
import hmac
import hashlib
import time
from threading import Thread
from websocket import create_connection, WebSocketConnectionClosedException
import psycopg2 as psql

# custom WebsocketClient implementation to support Mongo
class WebsocketClient(object):
    def __init__(self, url="wss://ws-feed.gdax.com", products=None,
            message_type="subscribe", mongo_collection=None, should_print=True,
            auth=False, api_key="", api_secret="", api_passphrase=""):
        self.url = url
        self.products = products
        self.type = message_type
        self.stop = False
        self.ws = None
        self.thread = None
        self.auth = auth
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.should_print = should_print
        self.mongo_collection = mongo_collection

    def start(self):
        def _go():
            self._connect()
            self._listen()

        self.stop = False
        self.on_open()
        self.thread = Thread(target=_go)
        self.thread.start()

    def _connect(self):
        if self.products is None:
            self.products = ["BTC-USD"]
        elif not isinstance(self.products, list):
            self.products = [self.products]

        if self.url[-1] == "/":
            self.url = self.url[:-1]

        sub_params = {'type': 'subscribe', 'product_ids': self.products}
        if self.auth:
            timestamp = str(time.time())
            message = timestamp + 'GET' + '/users/self'
            message = message.encode('ascii')
            hmac_key = base64.b64decode(self.api_secret)
            signature = hmac.new(hmac_key, message, hashlib.sha256)
            signature_b64 = base64.b64encode(signature.digest())
            sub_params['signature'] = signature_b64
            sub_params['key'] = self.api_key
            sub_params['passphrase'] = self.api_passphrase
            sub_params['timestamp'] = timestamp

        self.ws = create_connection(self.url)
        self.ws.send(json.dumps(sub_params))

        if self.type == "heartbeat":
            sub_params = {"type": "heartbeat", "on": True}
        else:
            sub_params = {"type": "heartbeat", "on": False}
        self.ws.send(json.dumps(sub_params))

    def _listen(self):
        while not self.stop:
            try:
                if int(time.time() % 30) == 0:
                    # Set a 30 second ping to keep connection alive
                    self.ws.ping("keepalive")
                msg = json.loads(self.ws.recv())
            except Exception as e:
                self.on_error(e) # this does not fix the broken connection issue
                self.close()
                self.start()
            else:
                self.on_message(msg)

    def close(self):
        if not self.stop:
            self.on_close()
            self.stop = True
            self.thread.join()
            try:
                if self.ws:
                    self.ws.close()
            except WebSocketConnectionClosedException as e:
                pass

    def on_open(self):
        if self.should_print:
            print("-- Subscribed! --\n")

    def on_close(self):
        if self.should_print:
            print("\n-- Socket Closed --")

    def on_message(self, msg):
        if self.should_print:
            print(msg)
        if self.mongo_collection: # dump JSON to given mongo collection
            self.mongo_collection.insert_one(msg)

    def on_error(self, e):
        print(e)

if __name__ == '__main__':

    # Properties
    CURRENCY_PAIR = 'BTC-USD'

    # Grab user-specific Postgres details
    with open('properties.json') as data:
        properties = json.load(data)
    ADDRESS = properties['ADDRESS']
    USER = properties['USER']
    PASSWORD = properties['PASSWORD']
    DATABASE_NAME = properties['DATABASE_NAME']

    # Postgres configuration
    try:
        conn = psql.connect("dbname=" + DATABASE_NAME + " user=" + USER + 
                            " host=" + ADDRESS + " password=" + PASSWORD)
    except:
        print "Cannot connect to the database"
    
    # # AWS and Mongo configuration
    # m = MongoClient('mongodb://' + USER + ':' + PASSWORD + '@' + ADDRESS + '/'
    #     + DATABASE_NAME)
    # db = m.db
    # btc = db.btc # this names the Mongo collection, if it does not already exist
    
    # begin streaming from GDAX
    wsClient = WebsocketClient(url="wss://ws-feed.gdax.com",
        products=CURRENCY_PAIR, mongo_collection=btc, should_print=False)
    wsClient.start()
