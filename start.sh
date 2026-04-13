#!/bin/bash
set -e

echo "=== See-through Serverless Worker ==="
echo "MODE_TO_RUN: $MODE_TO_RUN"
echo "HF_HOME: $HF_HOME"

# SSH 설정 (Pod 모드에서 접속용)
setup_ssh() {
    if [[ $PUBLIC_KEY ]]; then
        echo "Setting up SSH..."
        mkdir -p ~/.ssh
        echo "$PUBLIC_KEY" >> ~/.ssh/authorized_keys
        chmod 700 -R ~/.ssh
        ssh-keygen -A
        service ssh start
    fi
}

case $MODE_TO_RUN in
    serverless)
        echo "Starting in Serverless mode..."
        exec python -u /app/handler.py
        ;;
    pod)
        echo "Starting in Pod mode..."
        setup_ssh
        echo "SSH ready. You can test with: python /app/handler.py"
        sleep infinity
        ;;
    *)
        echo "Invalid MODE_TO_RUN: $MODE_TO_RUN (expected 'pod' or 'serverless')"
        exit 1
        ;;
esac