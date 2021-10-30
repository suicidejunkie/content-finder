import string
import random
import requests
import re
import json


class RandomFinder:
    def __init__(self) -> None:
        pass

    def find_random(self, size: int) -> str:
        if 0 > size > 10:
            size = 3

        rand_str = self._rand_str(size)
        url = f'https://www.youtube.com/results?search_query={rand_str}'
        resp = requests.get(url)

        # Thankfully the video data is stored as json in script tags
        # We just have to pull the json out...
        start = 'ytInitialData = '
        end = ';</script>'
        vids = json.loads(resp.text.split(start)[1].split(end)[0])
        vids = vids['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents']
        vids = [x for x in vids if 'videoRenderer' in x]

        try:
            rand_num = random.randrange(len(vids))
        except ValueError:
            return None

        return vids[rand_num]['videoRenderer']['videoId']

    def _rand_str(self, size: int) -> str:
        """
        Great func found here: https://stackoverflow.com/a/2257449 &
        https://stackoverflow.com/a/23728630
        We definitely don't need this to be crypto-secure but why not?
        """
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.SystemRandom().choice(chars) for _ in range(size))
