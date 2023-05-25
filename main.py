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
from functools import partial


def get_binary_size(program: SourceProgram, setting: CompilationSetting):
    return setting.compile_program(
        program, ObjectCompilationOutput(None)
    ).output.text_size()


def get_ratio(program: SourceProgram, setting: CompilationSetting):
    source_size = len(program.code)

    binary_size = get_binary_size(program, setting)
    return binary_size / source_size


def filter(
    program: SourceProgram,
    best_ratio: float,
    setting: CompilationSetting,
):
    current_ratio = get_ratio(program, setting)
    return current_ratio >= best_ratio


class ReduceBinaryRatio(ReductionCallback):
    def __init__(self, san: Sanitizer, ratio: int, setting: CompilationSetting) -> None:
        self.san = san
        self.ratio = ratio
        self.setting = setting

    def test(self, program: SourceProgram) -> bool:
        if not self.san.sanitize(program):
            return False
        return filter(program, self.ratio, self.setting)


class ReduceBinarySize(ReductionCallback):
    def __init__(self, san: Sanitizer, size: int, setting: CompilationSetting) -> None:
        self.san = san
        self.size = size
        self.setting = setting

    def test(self, program: SourceProgram) -> bool:
        if not self.san.sanitize(program):
            return False
        return get_binary_size(program, self.setting) >= self.size


if __name__ == "__main__":
    setting = CompilationSetting(
        compiler=CompilerExe.get_system_gcc(),
        opt_level=OptLevel.O0,
        flags=("-march=native",),
    )

    sanitizer = Sanitizer()
    generator = CSmithGenerator(
        sanitizer=sanitizer,
        include_path="/home/remo/csmith/include",
        csmith="/home/remo/csmith/bin/csmith",
        minimum_length=10,
    )
    generator.fixed_options += ["--stop-by-stmt", "100"]

    steps = 1
    initial_programs = 10
    programs_per_step = 1

    program_pool = []
    for i in range(initial_programs):
        p = generator.generate_program()
        p = setting.preprocess_program(p, make_compiler_agnostic=True)
        program_pool.append(p)

    for i in range(steps):
        ratio_with_setting = partial(get_ratio, setting=setting)
        p = max(program_pool, key=ratio_with_setting)
        ratio = get_ratio(p, setting)
        size = get_binary_size(p, setting)
        print(f"Current ration: {ratio}, Initial size: {size}")
        program_pool = []
        for j in range(programs_per_step):
            reduction = Reducer("/usr/bin/cvise").reduce(
                p, ReduceBinaryRatio(sanitizer, ratio, setting)
            )
            program_pool.append(reduction)
