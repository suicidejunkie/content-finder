import os
import sqlite3
from typing import OrderedDict
import requests
import socketio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from bs4 import BeautifulSoup as bs


load_dotenv()


class ContentFinder:
    def __init__(self) -> None:
        self.con = None  # Due to threading with sockets we can't init here...
        self.last_updated = None
        self.sio = socketio.Client()
        self.queue_resp = None
        self.queue_err = False  # To avoid issues with different threads (i.e. main and error thread) changing queue_resp
                                # while another thread is waiting for it to have a specific value
        self.lock = False

        self.url = os.getenv('CYTUBE_URL')
        self.channel_name = os.getenv('CYTUBE_URL_CHANNEL_NAME')
        self.cytube_username = os.getenv('CYTUBE_USERNAME')
        self.cytube_password = os.getenv('CYTUBE_PASSWORD')
        self.admins = os.getenv('ADMINS').split(',')

    def _init_db(self) -> None:
        self.con = sqlite3.connect('content.db')
        cur = self.con.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS content (channelId text primary key, name text, datetime text)')
        self.con.commit()

    def _init_socket(self) -> str:
        socketConfig = f'{self.url}socketconfig/{self.channel_name}.json'
        resp = requests.get(socketConfig)
        print(f'resp: {resp.status_code} - {resp.reason}')
        servers = resp.json()
        socket_url = ''

        for server in servers['servers']:
            if server['secure']:
                socket_url = server['url']
                break
        
        if not socket_url:
            raise socketio.exception.ConnectionError('Unable to find a secure socket to connect to')

        return socket_url

    def pop_db(self) -> None:
        print('pop_db')
        self._init_db()

        cur = self.con.cursor()

        updated = os.path.getmtime(os.path.dirname(os.path.realpath(__file__)))

        if self.last_updated is not None and self.last_updated == updated:
            print('File not updated, nothing to add to DB.')
            return

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
                    self.con.commit()
                except sqlite3.IntegrityError:
                    print(f'{name} already in db, skipping.')

        self.last_updated = updated
        self.con.close()

    def find_content(self) -> list:
        print('find_content()')
        self._init_db()
        content = []
        cur = self.con.cursor()

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
                update_cur = self.con.cursor()
                update_cur.execute('UPDATE content SET datetime = ? WHERE channelId = ?',
                                  (str(new_dt), channel_id,))
                self.con.commit()
                update_cur.close()
        cur.close()
        self.con.close()

        return content

    def listen(self) -> None:
        @self.sio.event
        def connect():
            print('Socket connected!')
            self.sio.emit('joinChannel', {'name': self.channel_name})

        @self.sio.on('channelOpts')
        def channel_opts(resp):
            print(resp)
            self.sio.emit('login', {'name': self.cytube_username, 'pw': self.cytube_password})

        @self.sio.on('login')
        def login(resp):
            print(resp)
            self.sio.emit('channelRanks')
            self.sio.emit('chatMsg', {'msg': 'Hello!'})

        @self.sio.on('channelRanks')
        def test(resp):
            print('test: ' + resp)

        @self.sio.on('chatMsg')
        def chat(resp):
            print(resp)
            chat_ts = datetime.fromtimestamp(resp['time']/1000)
            delta = datetime.now() - timedelta(seconds=20)
            if resp['msg'] == '!content' and chat_ts > delta:
                if self.lock:
                    self.sio.emit('chatMsg', {'msg': 'Already collecting content'})
                    return

                self.sio.emit('chatMsg', {'msg': 'Searching for content...'})

                self.lock = True
                self.pop_db()
                content_list = self.find_content()

                if not content_list:
                    print('**** No content to add ****')
                    self.sio.emit('chatMsg', {'msg': 'No content to add.'})
                else:
                    print(f'**** Videos to be added: {len(content_list)} ****')
                    self.sio.emit('chatMsg', {'msg': f'Adding {len(content_list)} videos.'})

                for content in content_list:
                    self.sio.emit('queue', {'id': content, 'type': 'yt', 'pos': 'end', 'temp': True})
                    # Wait for resp
                    while not self.queue_resp:
                        self.sio.sleep(0.3)
                    self.queue_resp = None
                self.lock = False
            elif resp['msg'] == '!kill' and resp['username'] in self.admins and chat_ts > delta:
                self.sio.emit('chatMsg', {'msg': 'Bye bye!'})
                self.sio.disconnect()

        @self.sio.on('queue')
        @self.sio.on('queueWarn')
        def queue(resp):
            """
            We're making the assumption that queueWarn is stuff like 'already in queue'
            and other senisble warning-esque messages i.e. that they're warnings that
            don't really matter to us because the content has been added.
            """
            print(f'queue: {resp}')
            self.queue_err = False
            self.queue_resp = resp

        @self.sio.on('queueFail')
        def queue_err(resp):
            self.queue_err = True
            print(f'queue err: {resp}')
            try:
                id = resp['id']
                self.sio.emit('chatMsg', {'msg': f'Failed to add {id}, retrying in 2 secs.'})
                self.sio.sleep(2)
                self.sio.emit('queue', {'id': id, 'type': 'yt', 'pos': 'end', 'temp': True})
                while self.queue_err:
                    self.sio.sleep(0.1)
            except KeyError as err:
                print('queue err doesn\'t contain key "id"')

        @self.sio.event
        def connect_error():
            print('Socket connection error. Attempting reconnect.')
            # socket_url = self._init_socket()
            # self.sio.connect(socket_url)

        @self.sio.event
        def disconnect():
            print('Socket disconnected. Attempting reconnect.')
            # socket_url = self._init_socket()
            # self.sio.connect(socket_url)

        socket_url = self._init_socket()
        self.sio.connect(socket_url)
        self.sio.wait()

if __name__ == '__main__':
    content = ContentFinder()
    content.listen()