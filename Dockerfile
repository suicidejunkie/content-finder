FROM node:12-buster-slim

WORKDIR /usr/src/app

COPY package*.json ./
RUN npm install

COPY app.js .

CMD ["npm", "run", "start"]