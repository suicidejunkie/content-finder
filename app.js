require('dotenv').config();

const fs = require('fs');
const LineByLineReader = require('line-by-line')
const sqlite3 = require('sqlite3').verbose();
const https = require('https');
const parseString = require('xml2js').parseString;
const io = require('socket.io-client')

// https.globalAgent.options.secureProtocol = 'SSLv3_method';

function initDb(_callback) {
    console.log('Initalising DB.')
    var sql = 'CREATE TABLE IF NOT EXISTS content (channelId text primary key, name text, datetime text)';
    db.run(sql, (err) => {
        if (err) {
            return console.error(err.message);
        }
        const rl = new LineByLineReader('channel-ids.txt');

        lines = [];
        rl.on('line', (line) => {
            lines.push(line);
            if (lines.length === 2) {
                rl.pause();
                const name = lines[0].substring(2, lines[0].length).trim();
                const channelId = lines[1].trim();

                // Get the most recent published date for the datetime in DB
                const options = {
                    host: 'www.youtube.com',
                    port: 443,
                    path: `/feeds/videos.xml?channel_id=${channelId}`,
                    method: 'GET'
                };
                https.request(options, (res) => {
                    var data = '';
                    res.on('data', (chunk) => {
                        data += chunk;
                    });

                    res.on('end', () => {
                        parseString(data, (err, result) => {
                            if (err) {
                                return console.log(err.message);
                            }
                            const published = result['feed']['entry'][0]['published'][0];
                            
                            sql = 'INSERT INTO content(channelId, name, datetime) VALUES(?,?,?)';
                            db.run(sql, [channelId, name, published], (err) => {
                                if (err) {
                                    if (err.code === 'SQLITE_CONSTRAINT') {
                                        // We don't want to return from this error because we're
                                        // expecting to see SQLITE_CONSTRAIT errors.
                                        console.log(`${name} already in DB, skipping.`);
                                    } else {
                                        return console.error(err.message)
                                    }
                                }
                                lines = [];
                                rl.resume();
                            });
                        });
                    });
                }).on('error', (err) => {
                    return console.log(err.message);
                }).end();
            }
        });

        rl.on('end', () => {
            return _callback()
        });
    });
}

function find_content(_callback) {
    var content = [];

    var sql = 'SELECT * FROM content';
    var prom = new Promise((resolve, reject) => {
        db.all(sql, (err, rows) => {
            if (err) {
                return console.error(err.message);
            }

            // var iterProm = new Promise((iterResolve, iterReject) => {
            rows.forEach((row, idx) => {
                // try {
                const channelId = row['channelId'];
                const name = row['name'];
                const dt = row['datetime'];
                console.log(`Getting content for ${name}`);

                const options = {
                    host: 'www.youtube.com',
                    port: 443,
                    path: `/feeds/videos.xml?channel_id=${channelId}`,
                    method: 'GET'
                };
                https.request(options, (res) => {
                    var data = '';
                    res.on('data', (chunk) => {
                        data += chunk;
                    });

                    res.on('end', () => {
                        parseString(data, (err, result) => {
                            if (err) {
                                return console.log(err.message);
                            }
                            const entries = result['feed']['entry'];
                            var newDt = undefined;

                            // var innerProm = new Promise((innerResolve, innerReject) => {
                            entries.every((entry) => {
                                const title = entry['title'][0];
                                if (title.includes('#shorts')) {
                                    console.log('Skipping #short.');
                                    return true; // continue
                                }

                                const published = entry['published'][0];

                                if (new Date(published) <= new Date(dt)) {
                                    console.log(`No more new content for ${name}`);
                                    // innerResolve();
                                    return false; // break
                                }

                                var videoId = entry['yt:videoId'][0];

                                // Insert in reverse order so vids are in the order they were released
                                content.unshift(videoId);

                                if (newDt == null) {
                                    newDt = published;
                                }
                                return true; // continue
                            });
                            Promise.all(entries).then(() => {
                                if (newDt !== null) {
                                    sql = 'UPDATE content SET datetime = ? WHERE channelId = ?'
                                    db.run(sql, [newDt, channelId], (err, rows) => {
                                        if (err) {
                                            return console.error(err.message);
                                        }
                                        if (idx === rows.length - 1) {
                                            // Resolve promise
                                            resolve();
                                        }
                                    });
                                }
                            });
                        });
                    });
                }).on('error', (err) => {
                    return console.log(err.message);
                }).end();
            });
        });
    });

    prom.then(() => {
        return _callback(content);
    });
}

function add_to_cytube(contentArr, _callback) {
    if (contentArr.length === 0) {
        return _callback();
    }
    
    url = process.env.CYTUBE_URL;
    channel_name = process.env.CYTUBE_URL_CHANNEL_NAME;
    cytube_username = process.env.CYTUBE_USERNAME;
    cytube_password = process.env.CYTUBE_PASSWORD;

    const options = {
        host: `${url}`,
        port: 443,
        path: `/socketconfig/${channel_name}.json`,
        method: 'GET'
    };
    console.log(options)
    https.request(options, (res) => {
        console.log('getting data');
        var data = '';
        res.on('data', (chunk) => {
            data += chunk;
        });

        res.on('end', () => {
            data = JSON.parse(data);
            console.log(`Got data: ${JSON.stringify(data)}`);
            const server_url = (data['servers'][0]['secure']) ? data['servers'][0]['url'] : data['servers'][1]['url'];
            console.log(`Server url: ${server_url}`)

            // Socket definitions
            var socket = io.connect(server_url, {
                reconnect: false,
                secure: true
            });

            socket.on('connect', (connRes) => {
                console.log(`Socket connected, res: ${connRes}`);
                socket.emit('joinChannel', {'name': channel_name});
            });

            socket.on('channelOpts', (res) =>{
                console.log(`Joined channel, res ${res}`);
                socket.emit('login', {"name": cytube_username, "pw": cytube_password});
            });

            socket.on('login', (res) => {
                console.log(`Logged in, res: ${res}`);
                contentArr.forEach((content) => {
                    socket.emit('queue', {"id": content, "type": "yt", "pos": "end", "temp": true});
                });
            });
        });
    }).on('error', (err) => {
        return console.log(err.message);
    }).end();
}

const db = new sqlite3.Database('content.db', (err) => {
    if (err) {
        return console.log(err.message);
    }
    console.log('Connected to DB')
    initDb(() => {
        find_content((contentArr) => {
            console.log(`Content to add: ${contentArr}`)
            add_to_cytube(contentArr, () => {
                // Close DB connection
                db.close((err) => {
                    if (err) {
                        return console.log(err.message);
                    }
                    console.log('DB connection closed successfully.');
                });
            });
        });
    });
});