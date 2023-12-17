#!/bin/sh
echo "Base Path: ${DATA_CHAT_BASE_PATH}"
echo "OpenAI Endpoint ${AZURE_OPENAI_ENDPOINT}"
echo "OpenAI Model ${AZURE_OPENAI_CHATGPT_MODEL}"
echo "Starting server..."
hypercorn main:app --bind 0.0.0.0:8000 --root-path=$DATA_CHAT_BASE_PATH 