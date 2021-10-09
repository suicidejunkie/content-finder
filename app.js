require('dotenv').config();

const sqlite3 = require('sqlite3').verbose();
let db = new sqlite3.Database('content.db', (err) => {
    if (err) {
        return console.error(err.message);
    }
    console.log('Connected to DB')
});

function initDb() {
    var sql = 'CREATE TABLE IF NOT EXISTS content (channelId text primary key, name text, datetime text)'
    db.run(sql, (err) => {
        if (err) {
            return console.error(err.message);
        }
    })
}

initDb();

db.close((err) => {
    if (err) {
        return console.error(err.message);
    }
    console.log('DB connection closed successfully.')
});