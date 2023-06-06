import json
import os
import tempfile
from itertools import combinations_with_replacement, islice
from time import time

from diopter.compiler import CompilationSetting, CompilerExe, OptLevel
from diopter.sanitizer import Sanitizer
from utils import ReduceRatio, ReducerWithArgs, get_ratio, read_sourcefile

if __name__ == "__main__":
    # config
    options_file = "all.json"
    combinations = 1
    csmith_bin = "/mnt/c/Users/Bifbof/git_repos/ast2023_project/csmith/2/bin/csmith"
    csmith_inc = "/mnt/c/Users/Bifbof/git_repos/ast2023_project/csmith/2/include"
    cvise_bin = "/usr/bin/cvise"
    cvise_group_file = os.path.realpath("tempfile.json")
    result_file = os.path.realpath("test_passes_results6.csv")
    program_dir = os.path.realpath("10_programs")
    compiler = CompilerExe.get_system_gcc()
    cs = CompilationSetting(
        compiler=compiler,
        opt_level=OptLevel.O1,
        flags=("-march=native",),
    )
    sanitizer = Sanitizer()  # bool checks all possible failures

    # read in set of options
    with open(options_file) as f:
        default_options = json.load(f)
    options = default_options["first"]
    options += default_options["main"]
    options += default_options["last"]
    unique_options = []
    for o in options:
        if o not in unique_options:
            unique_options.append(o)

    # "x" because I delted like 8 hours of computation once :]
    with open(result_file, "x") as f:
        f.write("selection,start_ratio,end_ratio,duration\n")

    # don't take too big r or it exponentially explodes
    # for bigger selection draw randomly
    # slice as I could not compute everything in one go
    all_possibilities = islice(enumerate(combinations_with_replacement(unique_options, r=combinations)), 118, None)
    
    store_options = {"first": [], "main": [], "last": []}
    for i, selection in all_possibilities:
        # with replacing only first -> application only happens once
        store_options["first"] = list(selection)
        with open(os.path.realpath("tempfile.json"), "w") as f:
            json.dump(store_options, f)
        for file in os.listdir(program_dir):
            print(i, list(selection))
            start_code = read_sourcefile(os.path.join(program_dir, file))
            start_ratio = get_ratio(start_code, cs)
            interestingness = ReduceRatio(sanitizer, cs, start_ratio)
            reducer = ReducerWithArgs(os.path.realpath("tempfile.json"), cvise_bin)
            # create temporary file that avoids infodump
            with tempfile.TemporaryFile() as f:
                start_time = time()
                end_code = reducer.reduce(start_code, interestingness, log_file=f)
                end_time = time()
            with open(result_file, "a") as f:
                f.write(f'"{list(selection)}",{start_ratio},{get_ratio(end_code, cs)},{end_time-start_time}\n')
    os.remove("tempfile.json")
