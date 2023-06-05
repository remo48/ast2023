import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import replace
from multiprocessing import cpu_count
from pathlib import Path

from diopter.compiler import CompilationSetting, ProgramType, SourceProgram
from diopter.reducer import ReductionCallback, make_interestingness_script
from diopter.sanitizer import Sanitizer
from static_globals.instrumenter import annotate_with_static

from utils import get_binary_size


class ReduceBinaryRatio(ReductionCallback):
    def __init__(
        self,
        san: Sanitizer,
        ratio: float,
        setting: CompilationSetting,
        tmpdir: str = None,
        save_temps=False,
        binary_threshold=100,
    ) -> None:
        self.san = san
        self.ratio = ratio
        self.setting = setting
        self.binary_threshold = binary_threshold

        if save_temps and tmpdir is None:
            raise AttributeError("tmpdir must be given if save_temps=True")
        self.tmpdir = Path(tmpdir).absolute()
        self.save_temps = save_temps

    def test(self, program: SourceProgram) -> bool:
        if not self.san.sanitize(program):
            return False

        program = annotate_with_static(program)

        binary_size = get_binary_size(program, self.setting)
        if (
            binary_size < self.binary_threshold
            or binary_size / len(program.code) < self.ratio
        ):
            return False

        if self.save_temps:
            filename = uuid.uuid4().hex + ".c"
            with open(self.tmpdir / filename, "w") as f:
                f.write(program.code)
        return True


class CreduceReducer:
    def __init__(self, creduce: str | None = None):
        self.creduce = creduce if creduce else "creduce"
        assert shutil.which(self.creduce), f"{self.creduce} is not executable"

    def reduce(
        self,
        program: ProgramType,
        interestingness_test: ReductionCallback,
        jobs: int | None = None,
        outdir=None,
        timeout=200,
    ) -> ProgramType | None:
        creduce_jobs = jobs if jobs else cpu_count()

        code_filename = "code" + program.language.to_suffix()
        interestingness_script = make_interestingness_script(
            interestingness_test, program, code_filename
        )

        old_dir = Path(os.getcwd()).absolute()
        outdir = Path(outdir)
        os.chdir(outdir)

        code_file = outdir / code_filename
        with open(code_file, "w") as f:
            f.write(program.code)

        script_path = outdir / "check.py"
        with open(script_path, "w") as f:
            print(interestingness_script, file=f)
        os.chmod(script_path, 0o770)
        # run creduce
        creduce_cmd = [
            self.creduce,
            "--n",
            f"{creduce_jobs}",
            str(script_path.name),
            str(code_file.name),
        ]

        try:
            tmpdir = Path(tempfile.mkdtemp())
            env = os.environ.copy()
            env.update({"TMPDIR": str(tmpdir.absolute())})

            subprocess.run(
                creduce_cmd, cwd=outdir, check=True, timeout=timeout, env=env
            )
        except subprocess.TimeoutExpired:
            logging.info("Cancel reduction: Timeout")
        except subprocess.CalledProcessError as e:
            logging.info(f"Failed to reduce code. Exception: {e}")
            return None
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
            os.chdir(old_dir)

        with open(code_file, "r") as f:
            reduced_code = f.read()

        return replace(program, code=reduced_code)
