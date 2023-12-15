#!/bin/sh
echo $DATA_CHAT_BASE_PATH
hypercorn main:app --bind 0.0.0.0:8000 --root-path=$DATA_CHAT_BASE_PATH