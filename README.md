# content-finder
## Overview
A simple chat bot for Cytube, goes through channels added to `channel-ids.txt` and adds new videos to cytube.
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
Optional `.env` config:
```
ADMINS=username1,username2  # Allows closing the bot from chat
                            # This is hopefully a temp solution
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
Assuming bash shell:
```
python -m virtualenv venv
source venv/Scripts/activate
pip install -r requirements.txt
python main.py
```
ctrl+c to kill script.