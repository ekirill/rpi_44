#!/bin/bash

PROJECT_DIR=DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"

source "${PROJECT_DIR}/camera.env"
export PYTHONPATH="${PROJECT_DIR}/ekhome"
python3 "${PROJECT_DIR}/ekhome/camera.py"
