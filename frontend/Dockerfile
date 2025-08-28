FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json rollup.config.js ./
COPY src ./src
COPY public ./public
RUN npm install
RUN npm run build
CMD ["npx", "sirv", "public", "--single", "--host", "0.0.0.0", "--port", "5000"]
