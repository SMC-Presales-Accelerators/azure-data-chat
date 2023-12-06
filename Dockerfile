# Stage 1: Build the frontend
FROM node:18 AS frontend
WORKDIR /app/frontend
COPY app/frontend/package*.json ./
RUN npm install
COPY app/frontend .
RUN npm run build

# Stage 2: Install Python requirements and copy code
FROM python:3.11 AS backend
WORKDIR /app/backend
COPY app/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app/backend .

# Stage 3: Install msodbc 18
FROM backend AS msodbc
RUN apt-get update && apt-get install -y curl gnupg2
RUN curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && curl https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list && apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql18

# Stage 4: Run hypercorn
FROM msodbc AS final
EXPOSE 8000
# ENV AZURE_OPENAI_CHATGPT_DEPLOYMENT="" AZURE_OPENAI_CHATGPT_DEPLOYMENT="" AZURE_OPENAI_CHATGPT_MODEL="" AZURE_OPENAI_RESOURCE_GROUP="" AZURE_OPENAI_SERVICE="" AZURE_OPENAI_API_KEY="" DATABASE_CONNECTION_STRING=""
WORKDIR /app
COPY --from=frontend /app/backend/static ./backend/static
COPY --from=backend /app/backend .
WORKDIR /app/backend
CMD ["hypercorn", "main:app"]