import os
import sqlite3
import requests
import socketio
import json
from datetime import datetime
from dotenv import load_dotenv
from bs4 import BeautifulSoup as bs


load_dotenv()

YT_BASE_URL = 'https://www.youtube.com/watch?v='

con = sqlite3.connect('content.db')

def init_db() -> None:
    """
    Reads from channel-ids.txt and inserts into DB. Inserts date of most recent video.
    
    channels-ids.txt must be in the form:
    # CHANNEL_NAME
    CHANNEL_ID
    # CHANNEL_NAME
    CHANNEL_NAME
    """
    cur = con.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS content (channelId text primary key, name text, datetime text)')
    con.commit()

    with open('channel-ids.txt') as file:
        for line in file:
            name = line[1:].strip()
            # this will raise StopIteration if you channel-ids doesn't have even lines
            # i.e. if someone doesn't read the readme
            channel_id = next(file).strip()

            # Get most recent published date for datetime in DB
            channel = f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
            resp = requests.get(channel)
            page = resp.text
            soup = bs(page, 'lxml')
            entry = soup.find_all('entry')[0]
            published = entry.find_all('published')[0].text

            try:
                cur.execute('INSERT INTO content(channelId, name, datetime) VALUES(?,?,?)',
                           (channel_id, name, published,))
                con.commit()
            except sqlite3.IntegrityError:
                print(f'{name} already in db, skipping.')
    cur.close()

def find_content() -> list:
    content = []
    cur = con.cursor()

    cur.execute('SELECT * FROM content')
    for row in cur:
        channel_id = row[0]
        name = row[1]
        dt = datetime.fromisoformat(row[2])
        print(f'Getting content for: {name}')
        
        channel = f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
        resp = requests.get(channel)
        page = resp.text
        soup = bs(page, 'lxml')

        new_dt = None
        for item in soup.find_all('entry'):
            if '#shorts' in item.find_all('title')[0].text:
                print('Skipping #short.')
                continue
            published = datetime.fromisoformat(item.find_all('published')[0].text)

            if published < dt or published == dt:
                print(f'No more new videos for {name}')
                break

            video_id = item.find_all('yt:videoid')[0].text
            
            # Insert in reverse order so vids are in the order they were
            content.insert(0, video_id)

            # Set new datetime for DB
            if not new_dt:
                new_dt = published

        if new_dt:
            # Update datetime in DB
            update_cur = con.cursor()
            update_cur.execute('UPDATE content SET datetime = ? WHERE channelId = ?',
                              (str(new_dt), channel_id,))
            con.commit()
            update_cur.close()
    cur.close()

    return content


def add_to_cytube(content_list: list) -> None:
    if not content_list:
        return

    print(f'Videos to be added: {len(content_list)}')
    url = os.getenv('CYTUBE_URL')
    channel_name = os.getenv('CYTUBE_URL_CHANNEL_NAME')
    cytube_username = os.getenv('CYTUBE_USERNAME')
    cytube_password = os.getenv('CYTUBE_PASSWORD')

    #JSON shitter 9k
    socketConfig = f'{url}socketconfig/{channel_name}.json'
    resp = requests.get(socketConfig)
    servers = json.loads(resp.text)
    socket_url = ""

    for server in servers['servers']:
        if server["secure"]:
            socket_url = server["url"]
            break # if first record is secure may as well break out of loop
        elif not server["secure"]:
            socket_url = server["url"]

    sio = socketio.Client()
    if socket_url:
        # built in events
        @sio.event
        def connect():
            print("I'm connected!")

        @sio.event
        def connect_error(data):
            print("The connection failed!")

        @sio.event
        def disconnect():
            print("I'm disconnected!")

        # Cytube events

        # rec'd when connected to channel
        @sio.on('channelOpts')
        def on_connect(resp):
            print(resp)

        # rec'd when logging in
        @sio.on('login')
        def on_connect(resp):
            print(resp)

        # playlist as json
        @sio.on('playlist')
        def on_connect(resp):
            print(resp)

        sio.connect(socket_url)
        print('sid is', sio.sid)
        sio.sleep(1)
        sio.emit('joinChannel', {'name': channel_name})
        sio.sleep(1)
        sio.emit('login', {"name": cytube_username, "pw": cytube_password})
        sio.sleep(1)
        for contents in content_list:
            sio.emit('queue', {"id": contents, "type": "yt", "pos": "end", "temp": True})
            sio.sleep(0.1)
        sio.disconnect()

if __name__ == '__main__':
    init_db()
    content = find_content()
    add_to_cytube(content)
