import argparse
import logging
import os
from datetime import datetime
from functools import partial
from pathlib import Path

from diopter.compiler import (
    CompilationSetting,
    CompilerExe,
    Language,
    OptLevel,
    SourceProgram,
)
from diopter.generator import CSmithGenerator
from diopter.sanitizer import Sanitizer
from static_globals.instrumenter import annotate_with_static

from reducer import CreduceReducer, ReduceBinaryRatio
from utils import get_ratio

COMPILER = {
    "gcc": CompilerExe.get_system_gcc(),
    "clang": CompilerExe.get_system_clang(),
}


def setup_experiment_folder(outdir: str):
    parent = Path(outdir).absolute()
    name = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_root = parent / name
    experiment_root.mkdir(parents=True)
    logging.info(f"Store experiment output in folder {experiment_root}")
    return experiment_root


def log_arguments(experiment_dir, args):
    with open(experiment_dir / "settings.log", "w") as f:
        f.write("Experiment settings:\n")
        for arg in vars(args):
            f.write(f"{arg}: {getattr(args, arg)}\n")


def get_best_program(program_dir: str, setting: CompilationSetting):
    best_ratio = 0
    best_program = None
    for file in os.listdir(program_dir):
        with open(os.path.join(program_dir, file), "r") as f:
            p = SourceProgram(
                code=f.read(),
                language=Language.C,
            )
            try:
                current_ratio = get_ratio(p, setting)
                if current_ratio > best_ratio:
                    best_ratio = current_ratio
                    best_program = p
            except:
                continue

    return best_program, best_ratio


def main(args):
    setting = CompilationSetting(
        compiler=COMPILER[args.compiler],
        opt_level=OptLevel.from_str(args.opt_level),
        flags=("-march=native",),
    )

    sanitizer = Sanitizer()
    generator = CSmithGenerator(
        sanitizer=sanitizer,
        include_path="/home/remo/csmith/include",
        csmith="/home/remo/csmith/bin/csmith",
        minimum_length=10,
    )
    generator.fixed_options += ["--stop-by-stmt", "100", "--no-volatiles"]

    reducer = CreduceReducer()

    program_pool = []
    generated = 0
    while generated < args.initial_programs:
        p = generator.generate_program()
        p = setting.preprocess_program(p, make_compiler_agnostic=True)
        if not "volatile" in p.code:
            program_pool.append(p)
            generated += 1
    p = max(program_pool, key=partial(get_ratio, setting=setting))

    rounds_no_improvement = 0
    experiment_root = setup_experiment_folder(args.out)
    log_arguments(experiment_root, args)
    for i in range(args.rounds):
        if rounds_no_improvement >= args.max_rounds_no_improvement:
            break

        iteration_dir = experiment_root / f"step_{i+1}"
        iteration_dir.mkdir()
        tmpdir = iteration_dir / "tmp"
        tmpdir.mkdir()

        p = annotate_with_static(p)
        best_ratio = get_ratio(p, setting)
        p = reducer.reduce(
            p,
            ReduceBinaryRatio(
                sanitizer,
                best_ratio,
                setting,
                save_temps=True,
                tmpdir=tmpdir,
                binary_threshold=args.threshold,
            ),
            outdir=iteration_dir,
            timeout=args.timeout,
        )

        step_p, step_ratio = get_best_program(tmpdir, setting)
        if step_ratio > best_ratio:
            p = step_p

        if get_ratio(p, setting) - best_ratio < args.min_improvement_per_round:
            rounds_no_improvement += 1
        else:
            rounds_no_improvement = 0

        with open(iteration_dir / "best.c", "w") as f:
            f.write(p.code)
        # shutil.rmtree(tmpdir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, required=True)
    parser.add_argument("--initial-programs", type=int, default=10)
    parser.add_argument(
        "--opt-level",
        type=str,
        choices=["O0", "O1", "O2", "O3", "Os", "Oz"],
        default="O0",
    )
    parser.add_argument("--compiler", type=str, choices=["gcc", "clang"], default="gcc")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out", type=str, default="out")
    parser.add_argument("--threshold", type=int, default=100)
    parser.add_argument("--max-rounds-no-improvement", type=int, default=3)
    parser.add_argument("--min-improvement-per-round", type=float, default=0.2)

    args = parser.parse_args()
    main(args)
