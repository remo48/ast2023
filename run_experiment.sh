#!/bin/bash

opt_levels=("O3" "Os")
compilers=("gcc" "clang")
timeouts=(300 400)
thresholds=(100 200)

for compiler in "${compilers[@]}"; do
  for opt_level in "${opt_levels[@]}"; do
    for timeout in "${timeouts[@]}"; do
      for threshold in "${thresholds[@]}"; do
        python main.py --rounds 10 --opt-level "$opt_level" --compiler "$compiler" --timeout "$timeout" --threshold "$threshold" --out out_2
      done
    done
  done
done