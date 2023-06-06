import json
import logging
import os
import re
import subprocess
from dataclasses import replace
from multiprocessing import cpu_count
from pathlib import Path
from shutil import which
from sys import stderr
from typing import TextIO

from diopter.compiler import (CompilationSetting, CompilerExe, Language,
                              ObjectCompilationOutput, OptLevel, SourceProgram)
from diopter.reducer import (Reducer, ReductionCallback,
                             make_interestingness_script)
from diopter.sanitizer import Sanitizer
from diopter.utils import TempDirEnv, run_cmd_to_logfile

from static_globals.instrumenter import annotate_with_static


def get_binary_size(program: SourceProgram, setting: CompilationSetting) -> int:
    """Use diopter to get .text size of program"""
    return setting.compile_program(
        program, ObjectCompilationOutput(None)
    ).output.text_size()


def get_code_size(program: SourceProgram) -> int:
    """Calculate number of words of size of SourceProgram filtering all,
      that don't start with alpha"""
    # return len([p for p in program.code.split() if re.match("^[a-zA-Z_]", p)])
    return len(program.code)


def get_ratio(program: SourceProgram, setting: CompilationSetting) -> float:
    """Divide code size by binary size"""
    return (get_binary_size(program, setting)) / get_code_size(program)


def filter(program: SourceProgram, comp: CompilationSetting, target_ratio: float) -> float:
    """Returns True if code size to binary size ratio is bigger than target ratio."""
    return get_ratio(program, comp) >= target_ratio


def read_sourcefile(file_path: str) -> SourceProgram:
    """Read *.c file and put it into SourceProgram"""
    with open(file_path) as f:
        code = f.read()
    return SourceProgram(code=code, language=Language.C)


class ReducerWithArgs(Reducer):
    """Copy of diopter Reducer class, with simple option to change pass_group_file manually"""

    def __init__(self, pass_group_file: str, creduce: str | None = None):
        """
        Args:
            pass_group_file (str):
            where replacement for group file is located
            creduce (str | None):
            path to the creduce binary, if empty "creduce" will be used
        """
        self.pass_group_file = pass_group_file
        self.creduce = creduce if creduce else "creduce"
        assert which(self.creduce), f"{self.creduce} is not executable"

    def reduce(
        self,
        program: SourceProgram,
        interestingness_test: ReductionCallback,
        jobs: int | None = None,
        log_file: TextIO | None = None,
        debug: bool = False,
    ) -> SourceProgram | None:
        """
        Reduce `program` according to the `interestingness_test`

        Args:
            program (SourceProgram):
                the program to reduce
            interestingness_test (ReductionCallback):
                a concrete ReductionCallback that implementes the interestingness
            jobs (int|None):
                The number of Creduce jobs, if empty cpu_count() will be
            log_file (TextIO | None):
                Where to log Creduce's output, if empty stderr will be used
            debug (bool):
                Whether to pass the debug flag to creduce

        Returns:
            (SourceProgram |None):
                Reduced program, if successful.
        """
        creduce_jobs = jobs if jobs else cpu_count()

        code_filename = "code" + program.language.to_suffix()

        interestingness_script = make_interestingness_script(
            interestingness_test, program, code_filename
        )

        # creduce likes to kill unfinished processes with SIGKILL
        # so they can't clean up after themselves.
        # Setting a temporary temporary directory for creduce to be able to clean
        # up everything
        with TempDirEnv() as tmpdir:
            code_file = tmpdir / code_filename
            with open(code_file, "w") as f:
                f.write(program.code)

            script_path = tmpdir / "check.py"
            with open(script_path, "w") as f:
                print(interestingness_script, file=f)
            os.chmod(script_path, 0o770)
            # run creduce
            creduce_cmd = [
                self.creduce,
                "--n",
                f"{creduce_jobs}",
                "--pass-group-file",
                f"{self.pass_group_file}",
                str(script_path.name),
                str(code_file.name),
            ]
            if debug:
                creduce_cmd.append("--debug")

            try:
                run_cmd_to_logfile(
                    creduce_cmd,
                    log_file=log_file if log_file else stderr,
                    working_dir=Path(tmpdir),
                    additional_env={"TMPDIR": str(tmpdir.absolute())},
                )
            except subprocess.CalledProcessError as e:
                logging.info(f"Failed to reduce code. Exception: {e}")
                return None

            with open(code_file, "r") as f:
                reduced_code = f.read()

            return replace(program, code=reduced_code)


class ReduceRatio(ReductionCallback):
    target_ratio: float

    def __init__(self, san: Sanitizer, comp: CompilationSetting, target_ratio: float):
        self.san = san
        self.comp = comp
        self.target_ratio = target_ratio

    def test(self, program: SourceProgram) -> bool:
        program = annotate_with_static(program)
        if not self.san.sanitize(program):
            return False
        if get_binary_size(program, self.comp) <= 100:
            return False
        return filter(program, self.comp, self.target_ratio)

    def update_target_ratio(self, target_ratio: int):
        if (self.target_ratio < target_ratio):
            raise ValueError("target_size cannot be bigger than previous one")
        self.target_ratio = target_ratio


def get_standard_compiler_settings() -> CompilationSetting:
    compiler = CompilerExe.get_system_gcc()
    return CompilationSetting(
        compiler=compiler,
        opt_level=OptLevel.Os,
        flags=("-march=native",),
    )

def write_pass_file(path, first=[], main=[], last=[]):
    pas = {"first": first, "main": main, "last": last}
    with open(path, "w") as f:
        json.dump(pas, f)
