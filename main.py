import os
from dotenv import load_dotenv
from chat_bot import ChatBot

load_dotenv()


def main():
    url = os.getenv('CYTUBE_URL')
    channel_name = os.getenv('CYTUBE_URL_CHANNEL_NAME')
    username = os.getenv('CYTUBE_USERNAME')
    password = os.getenv('CYTUBE_PASSWORD')

    bot = ChatBot(url, channel_name, username, password)
    bot.listen()


if __name__ == '__main__':
    main()
