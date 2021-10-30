import requests
from datetime import datetime
from bs4 import BeautifulSoup as bs
from cytubebot.contentfinder.database import DBHandler


class ContentFinder:
    def __init__(self) -> None:
        self.db = DBHandler()

    def find_content(self) -> tuple[dict, int]:
        """
        returns:
            A tuple containing the content dict and a count of the amount of
            new content found. Content dict comes in the form:
            {
                'channel_id': (datetime, [video_id_1, video_id_2])
            }
        """
        con, cur = self.db.init_db()
        content = {}
        count = 0

        cur.execute('SELECT * FROM content')
        for row in cur:
            channel_id = row[0]
            name = row[1]
            dt = datetime.fromisoformat(row[2])
            print(f'Getting content for: {name}')

            channel = ('https://www.youtube.com/feeds/videos.xml?channel_id='
                       f'{channel_id}')
            resp = requests.get(channel)
            page = resp.text
            soup = bs(page, 'lxml')

            video_ids = []
            new_dt = None
            for item in soup.find_all('entry'):
                if '#shorts' in item.find_all('title')[0].text.casefold():
                    print('Skipping #short.')
                    continue

                published = item.find_all('published')[0].text
                published = datetime.fromisoformat(published)

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
        con.close()

        return content, count
