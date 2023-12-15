#!/bin/sh
hypercorn main:app --bind 0.0.0.0:8000 --root-path=$DataChatBasePath