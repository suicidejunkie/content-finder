# content-finder

# Setup
## Env fie
Make `.env` with `CYTUBE_URL`, `CYTUBE_URL_CHANNEL_NAME`, `CYTUBE_USERNAME`, and `CYTUBE_PASSWORD`.

Something like:
```
CYTUBE_URL=https://cytu.be/
CYTUBE_URL_CHANNEL_NAME=my_channel
CYTUBE_USERNAME=my_username
CYTUBE_PASSWORD=my_password
```

## Channels
Add channel ids and channel names to `channel-ids.txt`, e.g.:
```
# channel name 1
channel_id_1
# channel name 2
channel_id_2
```

# Running
`docker-compose up`