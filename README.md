# content-finder
## Overview
A simple chat bot for Cytube, goes through channels added to `channel-ids.txt` and adds new videos to cytube.
## Requirements
- Docker - can be run without but recommended.
- Python 3.10 - if desparate not to install 3.10 for some reason then goto `cytubebot/chatbot/chat_bot` line ~113 and swap switch case for if-elif-else.
## Setup
### Env fie
Make `.env` with `CYTUBE_URL`, `CYTUBE_URL_CHANNEL_NAME`, `CYTUBE_USERNAME`, and `CYTUBE_PASSWORD`.

Example:
```
CYTUBE_URL=https://cytu.be/
CYTUBE_URL_CHANNEL_NAME=my_channel
CYTUBE_USERNAME=my_username
CYTUBE_PASSWORD=my_password
```
### Channels
Add channel ids and channel names to `channel-ids.txt`, e.g.:
```
# channel name 1
channel_id_1
# channel name 2
channel_id_2
```
## Running
I strongly recommend adding admins to the `.env` file and stopping the bot with `!kill` in chat.
### Docker compose
Start: `docker-compose up -d`
Stop: `docker-compose down`
### No docker
You **MUST** edit `DB_FILE` in `cytubebot/contentfinder/conf.ini` file correctly or everything will explode - I would recommend a full path but for relative, it must be relative to `cytube/contentfinder/database.py` (untested but `../../content.db` should work.)

Assuming bash shell on linux (for bash on windows `source venv/Scripts/activate`):
```
python -m virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
python cytubebot/main.py
```
ctrl+c to kill script.