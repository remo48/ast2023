from diopter.compiler import (
    CompilationSetting,
    CompilerExe,
    ObjectCompilationOutput,
    OptLevel,
    SourceProgram,
)
from diopter.generator import CSmithGenerator
from diopter.reducer import Reducer, ReductionCallback
from diopter.sanitizer import Sanitizer


def get_ratio(program: SourceProgram, setting: CompilationSetting):
    source_size = len(program.code)

    binary_size = setting.compile_program(
        program, ObjectCompilationOutput(None)
    ).output.text_size()
    return binary_size / source_size


def filter(program: SourceProgram, best_ratio: int, setting: CompilationSetting):
    program_ratio = get_ratio(program, setting)
    print(program_ratio)
    return program_ratio > best_ratio


class ReduceBinaryRatio(ReductionCallback):
    def __init__(self, san: Sanitizer, ratio: int) -> None:
        self.san = san
        self.ratio = ratio

    def test(self, program: SourceProgram) -> bool:
        if not self.san.sanitize(program):
            return False
        return filter(program, self.ratio)


if __name__ == "__main__":
    setting = CompilationSetting(
        compiler=CompilerExe.get_system_gcc(), opt_level=OptLevel.O0
    )

    sanitizer = Sanitizer()
    while True:
        p = CSmithGenerator(
            sanitizer=sanitizer,
            include_path="/home/remo/csmith/include",
            csmith="/home/remo/csmith/bin/csmith",
        ).generate_program()
        p = setting.preprocess_program(p)
        if filter(p, 0, setting):
            break

    initial_ratio = get_ratio(p, setting)
    rprogram = Reducer().reduce(p, ReduceBinaryRatio(sanitizer, initial_ratio))
