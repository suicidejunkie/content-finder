import os
import sqlite3
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
        self.sio = socketio.Client()  # For debugging: engineio_logger=True
        self.queue_resp = None
        self.queue_err = False  # To avoid issues with different threads (i.e. main and error thread) changing queue_resp
                                # while another thread is waiting for it to have a specific value
        self.lock = False
        self.users = {}
        self.valid_commands = ['!content', '!kill']

        self.url = os.getenv('CYTUBE_URL')
        self.channel_name = os.getenv('CYTUBE_URL_CHANNEL_NAME')
        self.cytube_username = os.getenv('CYTUBE_USERNAME')
        self.cytube_password = os.getenv('CYTUBE_PASSWORD')

    def _init_db(self) -> None:
        """
        Establish connection to DB, access via self.con
        """
        self.con = sqlite3.connect('content.db')
        cur = self.con.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS content (channelId text primary key, name text, datetime text)')
        self.con.commit()
        cur.close()

    def _init_socket(self) -> str:
        """
        Finds the socket conn for channel given in .env -  this method does NOT connect.

        returns:
            socket_url: str containing the url of the socket server
        """
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
        """
        Reads from channel-ids.txt and inserts into DB. Inserts date of most recent video.
    
        channels-ids.txt must be in the form:
        # CHANNEL_NAME
        CHANNEL_ID
        # CHANNEL_NAME
        CHANNEL_NAME
        """
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
        cur.close()
        self.con.close()

    def find_content(self) -> list:
        self._init_db()
        content = {}  # content = {id: (datetime, [video_id_1, video_id_2...])}
        count = 0
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

            video_ids = []
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
                video_ids.insert(0, video_id)

                # Set new datetime for DB
                if not new_dt:
                    new_dt = published

            count += len(video_ids)
            content[channel_id] = (new_dt, video_ids)

        cur.close()
        self.con.close()

        return content, count

    def listen(self) -> None:
        """
        Main 'loop', connects to the socket server from _init_socket() and waits for chat
        commands.

        Current commands:
            - !content
            - !kill
        """
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
            # self.sio.emit('channelRanks')
            self.sio.emit('chatMsg', {'msg': 'Hello!'})

        @self.sio.on('userlist')
        def userlist(resp):
            for user in resp:
                self.users[user['name']] = user['rank']

        @self.sio.on('addUser')
        @self.sio.on('setUserRank')
        def user_add(resp):
            self.users[resp['name']] = resp['rank']

        @self.sio.on('userLeave')
        def user_leave(resp):
             # Avoiding del since we don't really care if a user who left isn'tin the dict
            self.users.pop(resp['name'], None)

        @self.sio.on('chatMsg')
        def chat(resp):
            print(resp)
            chat_ts = datetime.fromtimestamp(resp['time']/1000)
            delta = datetime.now() - timedelta(seconds=10)

            # Ignore older messages and messages that aren't valid commands
            if chat_ts < delta or resp['msg'] not in self.valid_commands:
                return

            if self.users.get(resp['username'], 0) < 3:
                self.sio.emit('chatMsg', {'msg': 'You don\'t have permission to do that.'})
                return

            if self.lock:
                self.sio.emit('chatMsg', {'msg': 'Currently collecting content, please wait...'})
                return

            if resp['msg'] == '!content':
                self._init_db()
                cur = self.con.cursor()

                self.sio.emit('chatMsg', {'msg': 'Searching for content...'})

                self.lock = True
                self.pop_db()
                content, count = self.find_content()

                if count == 0:
                    print('**** No content to add ****')
                    self.sio.emit('chatMsg', {'msg': 'No content to add.'})
                else:
                    print(f'**** Videos to be added: {count} ****')
                    self.sio.emit('chatMsg', {'msg': f'Adding {count} videos.'})

                    for key, val in content.items():
                        new_dt = val[0]
                        content_list = val[1]
                    

                        for content in content_list:
                            self.sio.emit('queue', {'id': content, 'type': 'yt', 'pos': 'end', 'temp': True})
                            # Wait for resp
                            while not self.queue_resp:
                                self.sio.sleep(0.3)
                            self.queue_resp = None

                        cur.execute('UPDATE content SET datetime = ? WHERE channelId = ?',
                                          (str(new_dt), key,))
                        self.con.commit()
                    
                    # Close thread sensitive resources & unlock
                    cur.close()
                    self.con.close()
                    self.lock = False

                    self.sio.emit('chatMsg', {'msg': 'Finished adding content.'})
            elif resp['msg'] == '!kill':
                self.lock = True
                self.sio.emit('chatMsg', {'msg': 'Bye bye!'})
                self.sio.sleep(3)  # temp sol to allow the chat msg to send
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
            except KeyError:
                print('queue err doesn\'t contain key "id"')

        @self.sio.event
        def connect_error():
            print('Socket connection error. Attempting reconnect.')
            socket_url = self._init_socket()
            self.sio.connect(socket_url)

        @self.sio.event
        def disconnect():
            print('Socket disconnected.')
            # socket_url = self._init_socket()
            # self.sio.connect(socket_url)

        socket_url = self._init_socket()
        self.sio.connect(socket_url)
        self.sio.wait()

if __name__ == '__main__':
    content = ContentFinder()
    content.listen()