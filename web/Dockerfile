FROM node:22-slim

WORKDIR /app

COPY web/package.json ./package.json
RUN npm install --omit=dev

COPY web ./

ENV NEXT_PUBLIC_API_URL=http://localhost:8000

CMD ["npm", "run", "dev"]
