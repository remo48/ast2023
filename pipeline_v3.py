import json
import os
import random

from diopter.compiler import SourceProgram
from diopter.sanitizer import Sanitizer
from static_globals.instrumenter import annotate_with_static

from utils_passes import ReduceRatio, ReducerWithArgs, get_ratio, read_sourcefile, get_standard_compiler_settings, write_pass_file

if __name__ == '__main__':
    # #programs to consider to find an interesting start program
    nstartp = 10
    # #rounds to recursively search for better ratios
    nrounds = 20
    # #children with different reductions -> does not work really probably set seed or something
    nchildr = 5

    csmith_bin = "/mnt/c/Users/Bifbof/git_repos/ast2023_project/csmith/2/bin/csmith"
    csmith_inc = "/mnt/c/Users/Bifbof/git_repos/ast2023_project/csmith/2/include"
    cvise_bin = "/usr/bin/cvise"

    default_options_file = "all.json"
    slow_useful_file = "pass_data/slow_useful.json"
    fast_maybe_useful_file = "pass_data/fast_maybe_useful.json"
    # need to be real path as we pass them to cvise
    fast_options_pass_file = os.path.realpath("pass_data/fast_options_pass.json")
    slow_useful_pass_file = os.path.realpath("pass_data/slow_useful_pass.json")
    final_pass_file = os.path.realpath("pass_data/final_pass.json")
    lines_0_pass_file = os.path.realpath("pass_data/lines_0.json")

    with open(default_options_file) as f:
        default_options = json.load(f)
    with open(slow_useful_file) as f:
        slow_useful = json.load(f)
    with open(fast_maybe_useful_file) as f:
        fast_maybe_useful = json.load(f)

    # create fast_options first, will always stay the same
    fast_options = []
    # take order of default options for fast ones -> to be faster
    for option in default_options["first"]:
        if option in fast_maybe_useful:
            fast_options.append(option)
    # add all other options (skip all non-last things)
    for option in fast_maybe_useful:
        if (option not in fast_options) and (option not in default_options["last"]):
            fast_options.append(option)
    
    # try out lines - 0 just for funs
    write_pass_file(lines_0_pass_file, first=[{"pass": "lines", "arg": "0"}])

    write_pass_file(fast_options_pass_file, first=fast_options)

    cs = get_standard_compiler_settings()
    # change to [-10:]
    for filenr, file in enumerate(os.listdir("bigbinaries")[-6:], 4):
        # csmith = CSmithGenerator(sanitizer, csmith_bin, csmith_inc)
        # csmith.fixed_options += ["--stop-by-stmt",  "100"]
        # csmith = CSmithGenerator(sanitizer, csmith_bin, csmith_inc)
        # queue = []
        # for i in range(nstartp):
        #     p = csmith.generate_program()
        #     p = cs.preprocess_program(p, make_compiler_agnostic=True)
        #     print(f"{i}: found program with ratio {get_ratio(p, cs)}")
        #     queue.append(p)
    #for filenr, file in enumerate(["program95.c"]):
        sanitizer = Sanitizer()  # bool checks all possible failures
        code = read_sourcefile(f"bigbinaries/{file}")
        queue = [code]
        print("start with program " f"bigbinaries/{file} into file results_{filenr}_xx.c")
        for round in range(nrounds):
            p: SourceProgram = max(queue, key=lambda x: get_ratio(x, cs))
            queue = []
            p = annotate_with_static(p)
            ratio = get_ratio(p, cs)
            interestingness = ReduceRatio(sanitizer, cs, ratio)
            p = ReducerWithArgs(fast_options_pass_file, cvise_bin).reduce(p, interestingness)
            # apply fast options first
            ratio = get_ratio(p, cs)

            interestingness = ReduceRatio(sanitizer, cs, ratio)            
            p = ReducerWithArgs(lines_0_pass_file, cvise_bin).reduce(p, interestingness)
            ratio = get_ratio(p, cs)
            interestingness = ReduceRatio(sanitizer, cs, ratio)
            print(ratio)
            print(f"ratio of round {round}: {ratio}")
            with open(f"c_results3/results{filenr}_{round}.c", "w") as f:
                f.write(f"// ratio {ratio}\n")
                f.write(p.code)
            for c in range(nchildr):
                # prepare now pass file for slow pass
                pas = random.choice(slow_useful)
                write_pass_file(slow_useful_pass_file, first=[pas])
                # apply single slow pass and pray it does not take that long
                newp = ReducerWithArgs(slow_useful_pass_file, cvise_bin).reduce(p, interestingness)
                assert newp
                queue.append(newp)
    
    p: SourceProgram = max(queue, key=lambda x: get_ratio(x, cs))
    ratio = get_ratio(p, cs)
    interestingness = ReduceRatio(sanitizer, cs, ratio)
    with open(final_pass_file) as f:
        default_options["first"] = []
        default_options["main"] = []
        json.dump(default_options, f)
    p = ReducerWithArgs(fast_options_pass_file, cvise_bin).reduce(p, interestingness)

    with open("c_results/result_final.c", "w") as f:
        f.write(f"// ratio {get_ratio(p, cs)}\n")
        f.write(p.code)
    print(f"end ratios: {[get_ratio(p, cs) for p in queue]}")
