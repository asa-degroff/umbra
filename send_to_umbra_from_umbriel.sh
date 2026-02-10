#!/bin/bash
# Send a message from Umbriel to Umbra, with reply instructions appended.
# Usage: ./send_to_umbra_from_umbriel.sh "Your message here"

cd /home/asa/umbra
source .venv/bin/activate

MESSAGE="$1

[This message is from Umbriel, your technical advisor. To reply, use the ask_umbriel tool.]"

python send_to_umbra.py "$MESSAGE"
