import os
from dotenv import load_dotenv
from cytubebot.chatbot.chat_bot import ChatBot
from cytubebot.common.exceptions import MissingEnvVar

load_dotenv()


def main():
    url = os.getenv('CYTUBE_URL')
    channel_name = os.getenv('CYTUBE_URL_CHANNEL_NAME')
    username = os.getenv('CYTUBE_USERNAME')
    password = os.getenv('CYTUBE_PASSWORD')

    if not all([url, channel_name, username, password]):
        raise MissingEnvVar('One/some of the env variables are missing.')

    bot = ChatBot(url, channel_name, username, password)
    bot.listen()


if __name__ == '__main__':
    main()
