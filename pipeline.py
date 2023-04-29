from diopter.compiler import (
    CompilationSetting,
    CompilerExe,
    ExeCompilationOutput,
    Language,
    ObjectCompilationOutput,
    OptLevel,
    SourceProgram)

from diopter.reducer import Reducer
from diopter.sanitizer import Sanitizer
from diopter.generator import CSmithGenerator
from diopter.reducer import Reducer, ReductionCallback


def get_binary_size(program: SourceProgram, setting: CompilationSetting) -> int:
    return setting.compile_program(
        program, ObjectCompilationOutput(None)
    ).output.text_size()

def get_code_size(program: SourceProgram) -> int:
    return len(program.code)

def get_ratio(program: SourceProgram, setting: CompilationSetting) -> float:
    return get_binary_size(program, setting) / get_code_size(program)


def filter(program: SourceProgram, comp: CompilationSetting, target_ratio: float):
    return get_ratio(program, comp) >= target_ratio


class ReduceRatio(ReductionCallback):
    target_ratio: float

    def __init__(self, san: Sanitizer, comp: CompilationSetting, target_ratio: float):
        self.san = san
        self.comp = comp
        self.target_ratio = target_ratio

    def test(self, program: SourceProgram) -> bool:
        if not self.san.sanitize(program):
            return False
        return filter(program, self.comp, self.target_ratio)
    
    def update_target_ratio(self, target_ratio: int):
        if (self.target_ratio < target_ratio):
            raise ValueError("target_size cannot be bigger than previous one")
        self.target_ratio = target_ratio


if __name__ == '__main__':
    compiler = CompilerExe.get_system_gcc()
    cs = CompilationSetting(
        compiler=compiler,
        opt_level=OptLevel.O0,
        flags=("-march=native",),
    )
    # output = res.output.run()
    sanitizer = Sanitizer() # if all false then no problem
    csmith_bin = "/mnt/c/Users/Bifbof/git_repos/ast2023_project/csmith/2/bin/csmith"
    csmith_inc = "/mnt/c/Users/Bifbof/git_repos/ast2023_project/csmith/2/include"
    csmith = CSmithGenerator(sanitizer, csmith_bin, csmith_inc)
    csmith.fixed_options += ["--stop-by-stmt",  "1000"]
    minr = -float("inf")
    # find an interesting program
    for i in range(10):
        p = csmith.generate_program()
        p = cs.preprocess_program(p, make_compiler_agnostic=True)
        print("find program")
        ratio = get_ratio(p, cs)
        if ratio > minr:
            minr = ratio
            minp = p
    
    print(f"start ratio: {minr}")
    r = ReduceRatio(sanitizer, cs, minr)
    children = []
    for i in range(10):
        rprogram = Reducer().reduce(minp, r)
        assert rprogram
        children.append(rprogram)
    
    print(f"end ratios: {(get_ratio(p, cs) for p in children)}")
