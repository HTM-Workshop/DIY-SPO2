#!/bin/bash
mkdir -p profile
python3 -m cProfile -s tottime main.py > profile/$(date +%s).txt
