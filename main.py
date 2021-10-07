import os
import time
import sqlite3
import requests
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
cur.execute('CREATE TABLE IF NOT EXISTS content (videoId TEXT)')
con.commit()

def find_content() -> list:
    content = []
    with open('channel-ids.txt') as file:
        while (channel := file.readline().rstrip()):
            if channel.startswith('#'):
                continue
            print(f'Getting content for channel id: {channel}')
            channel = f'https://www.youtube.com/feeds/videos.xml?channel_id={channel}'
            resp = requests.get(channel)
            page = resp.text
            soup = bs(page, 'lxml')

            limit = 4
            i = 0
            for item in soup.find_all('entry'):
                if '#shorts' in item.find_all('title')[0].text:
                    print('Skipping #short :)')
                    continue
                for video_id in item.find_all('yt:videoid'):
                    if i == limit:
                        continue
                    i += 1

                    video_id = video_id.text

                    # If we've already seen it then let's skip it
                    cur.execute('SELECT * FROM content where videoId=(?)', (video_id,))
                    if len(cur.fetchall()) != 0:
                        print('Already seen this video, skipping: {}'.format(video_id))
                        continue

                    # Insert in reverse order so vids are in the order they were
                    # released in (mainly for wranglerstar)
                    content.insert(0, f'https://www.youtube.com/watch?v={video_id}')

                    # Insert into db
                    cur.execute('INSERT INTO content(videoId) VALUES(?)', (video_id,))
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

    # login - if fails to login, assume already logged in :)
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
    content = find_content()
    add_to_cytube(content)
