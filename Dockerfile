# Stage 1: Build the frontend
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY app/frontend .
RUN npm install && npm run build

# Stage 2: Install Python requirements and copy code
FROM python:3.12-alpine AS backend
WORKDIR /app/backend
COPY app/backend .
RUN apk update
RUN apk add gcc libc-dev g++ libffi-dev libxml2 unixodbc-dev curl
RUN pip install --no-cache-dir -r requirements.txt


# Stage 3: Install msodbc 18
FROM backend AS msodbc
WORKDIR /app/msodbc
RUN curl -O https://download.microsoft.com/download/7/6/d/76de322a-d860-4894-9945-f0cc5d6a45f8/msodbcsql18_18.4.1.1-1_amd64.apk && apk add --allow-untrusted msodbcsql18_18.4.1.1-1_amd64.apk

# Stage 4: Run hypercorn
FROM msodbc AS final
# ENV AZURE_OPENAI_CHATGPT_DEPLOYMENT="" AZURE_OPENAI_CHATGPT_DEPLOYMENT="" AZURE_OPENAI_CHATGPT_MODEL="" AZURE_OPENAI_RESOURCE_GROUP="" AZURE_OPENAI_SERVICE="" AZURE_OPENAI_API_KEY="" DATABASE_CONNECTION_STRING=""
WORKDIR /app
COPY --from=frontend /app/backend/static ./backend/static
COPY --from=backend /app/backend .
WORKDIR /app/backend
RUN chmod +x run.sh
EXPOSE 8000
CMD ["sh", "-c", "./run.sh"]