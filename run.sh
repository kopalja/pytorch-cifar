#!/bin/bash

python main.py --run_name baseline_dla --overshoot 0

python main.py --run_name overshoot_dla --overshoot 5

python main.py --run_name overshoot_dla --overshoot 3

python main.py --run_name overshoot_dla --overshoot 0.9
