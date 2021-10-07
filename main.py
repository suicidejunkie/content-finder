import os
import time
import sqlite3
import requests
from datetime import datetime
from dotenv import load_dotenv
from bs4 import BeautifulSoup as bs
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException


load_dotenv()

YT_BASE_URL = 'https://www.youtube.com/watch?v='


con = sqlite3.connect('content.db')
cur = con.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS content (channelId text primary key, name text, datetime text)')
con.commit()

def init_db() -> None:
    """
    Reads from channel-ids.txt and inserts into DB. Inserts date of most recent video.
    
    channels-ids.txt must be in the form:
    # CHANNEL_NAME
    CHANNEL_ID
    # CHANNEL_NAME
    CHANNEL_NAME
    """
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

def find_content() -> list:
    content = []

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
            content.insert(0, f'https://www.youtube.com/watch?v={video_id}')

            # Set new datetime for DB
            if not new_dt:
                new_dt = published
        
        if new_dt:
            # Update datetime in DB
            cur.execute('UPDATE content SET datetime = ? WHERE channelId = ?',
                       (str(new_dt), channel_id,))
            con.commit()

    return content


def add_to_cytube(content_list: list) -> None:
    if not content_list:
        return

    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--profile-directory=Default')
    chrome_options.add_argument('--user-data-dir=~/.config/google-chrome')

    driver = webdriver.Chrome(options=chrome_options)
    driver.delete_all_cookies()
    url = os.getenv('CYTUBE_URL')
    driver.get(url)

    # wait for load
    while True:
        try:
            WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.ID, 'chanjs-allow-prompt')))
            break
        except TimeoutException:
            print('waiting for page to load...')

    # login - if fails to login, assume already logged in.
    try:
        username = os.getenv('CYTUBE_USERNAME')
        password = os.getenv('CYTUBE_PASSWORD')
        u = driver.find_element_by_id('username')
        u.send_keys(username)
        p = driver.find_element_by_id('password')
        p.send_keys(password)
        p.send_keys(Keys.ENTER)
    except Exception:
        pass

    # wait for load (login causes reload)
    while True:
        try:
            WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.ID, 'chanjs-allow-prompt')))
            break
        except TimeoutException:
            print('waiting for page to load...')

    # Open mediaurl
    driver.find_element_by_id('showmediaurl').click()

    # add content to end of queue
    for content in content_list:
        print(f'Adding content to cytube: {content}')
        mediaurl = driver.find_element_by_id('mediaurl')
        mediaurl.send_keys(content)
        driver.find_element_by_id('queue_end').click()
        time.sleep(2)

    # Done - enjoy your content :)
    driver.quit()


if __name__ == '__main__':
    init_db()
    content = find_content()
    add_to_cytube(content)
