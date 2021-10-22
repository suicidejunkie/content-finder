import requests
import socketio
from datetime import datetime, timedelta
from exceptions import MissingEnvVar
from database import DBHandler
from content_finder import ContentFinder


class ChatBot:
    def __init__(self, url, channel_name, username, password) -> None:
        self.url = url
        self.channel_name = channel_name
        self.username = username
        self.password = password

        if not all([self.url, self.channel_name, self.username,
                    self.password]):
            raise MissingEnvVar('One/some of the env variables are missing.')

        self.sio = socketio.Client()  # For debugging: engineio_logger=True
        self.queue_resp = None

        # To avoid issues with different threads (i.e. main and error thread)
        # changing queue_resp while another thread is waiting for it to have a
        # specific value
        self.queue_err = False
        self.lock = False
        self.users = {}
        self.valid_commands = ['!content', '!kill']
        self.db = DBHandler()
        self.content_finder = ContentFinder()

    def _init_socket(self) -> str:
        """
        Finds the socket conn for channel given in .env -  this method does NOT
        connect.

        returns:
            A str containing the url of the socket server.
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
            raise socketio.exception.ConnectionError('Unable to find a secure '
                                                     'socket to connect to')

        return socket_url

    def listen(self) -> None:
        """
        Main 'loop', connects to the socket server from _init_socket() and
        waits for chat commands.

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
            self.sio.emit('login', {'name': self.username,
                                    'pw': self.password})

        @self.sio.on('login')
        def login(resp):
            print(resp)
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
                msg = 'You don\'t have permission to do that.'
                self.sio.emit('chatMsg', {'msg': msg})
                return

            if self.lock:
                msg = 'Currently collecting content, please wait...'
                self.sio.emit('chatMsg', {'msg': msg})
                return

            if resp['msg'] == '!content':
                con, cur = self.db.init_db()

                self.sio.emit('chatMsg', {'msg': 'Searching for content...'})

                self.lock = True
                self.db.pop_db()
                content, count = self.content_finder.find_content()

                if count == 0:
                    print('**** No content to add ****')
                    self.sio.emit('chatMsg', {'msg': 'No content to add.'})
                    return

                print(f'**** Videos to be added: {count} ****')
                self.sio.emit('chatMsg', {'msg': f'Adding {count} videos.'})

                for key, val in content.items():
                    new_dt = val[0]
                    content_list = val[1]

                    for content in content_list:
                        self.sio.emit('queue', {'id': content, 'type': 'yt',
                                                'pos': 'end', 'temp': True})
                        # Wait for resp
                        while not self.queue_resp:
                            self.sio.sleep(0.3)
                        self.queue_resp = None

                    if new_dt:
                        query = ('UPDATE content SET datetime = ? WHERE '
                                 'channelId = ?')
                        cur.execute(query, (str(new_dt), key,))
                        con.commit()

                # Close thread sensitive resources & unlock
                cur.close()
                con.close()
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
            print(f'queue: {resp}')
            self.queue_err = False
            self.queue_resp = resp

        @self.sio.on('queueFail')
        def queue_err(resp):
            if resp['msg'] == 'This item is already on the playlist':
                self.queue_resp = resp
                return

            self.queue_err = True
            print(f'queue err: {resp}')
            try:
                id = resp['id']
                self.sio.emit('chatMsg', {'msg': f'Failed to add {id}, '
                                          'retrying in 2 secs.'})
                self.sio.sleep(2)
                self.sio.emit('queue', {'id': id, 'type': 'yt', 'pos': 'end',
                                        'temp': True})
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

        socket_url = self._init_socket()
        self.sio.connect(socket_url)
        self.sio.wait()
