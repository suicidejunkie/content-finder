import sqlite3
import os
import requests
from bs4 import BeautifulSoup as bs


class DBHandler:
    def __init__(self) -> None:
        self.last_updated = None

    def init_db(self) -> tuple[sqlite3.Connection, sqlite3.Cursor]:
        """
        Opens and returns an open DB conn and cursor.

        returns:
            A tuple containing a connection to the DB and a cursor.
        """
        con = sqlite3.connect('content.db')
        cur = con.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS content (channelId text '
                    'primary key, name text, datetime text)')
        con.commit()

        return con, cur

    def pop_db(self) -> None:
        """
        Reads from channel-ids.txt and inserts into DB. Inserts date of most
        recent video.

        channels-ids.txt must be in the form:
        # CHANNEL_NAME
        CHANNEL_ID
        # CHANNEL_NAME
        CHANNEL_NAME
        """
        con, cur = self.init_db()

        updated = os.path.getmtime(os.path.dirname(os.path.realpath(__file__)))

        if self.last_updated is not None and self.last_updated == updated:
            print('File not updated, nothing to add to DB.')
            return

        with open('channel-ids.txt') as file:
            for line in file:
                name = line[1:].strip()
                # this will raise StopIteration if you channel-ids doesn't have
                # even lines i.e. if someone doesn't read the readme
                channel_id = next(file).strip()

                # Get most recent published date for datetime in DB
                channel = ('https://www.youtube.com/feeds/videos.xml?'
                           f'channel_id={channel_id}')
                resp = requests.get(channel)
                page = resp.text
                soup = bs(page, 'lxml')
                entry = soup.find_all('entry')[0]
                published = entry.find_all('published')[0].text

                try:
                    query = ('INSERT INTO content(channelId, name, datetime) '
                             'VALUES(?,?,?)')
                    cur.execute(query, (channel_id, name, published,))
                    con.commit()
                except sqlite3.IntegrityError:
                    print(f'{name} already in db, skipping.')

        self.last_updated = updated
        cur.close()
        con.close()
