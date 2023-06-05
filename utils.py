import json
import os
import logging
from pathlib import Path
import argparse
from datetime import datetime
from types import SimpleNamespace
from diopter.compiler import (
    CompilationSetting,
    ObjectCompilationOutput,
    SourceProgram,
)


class ExperimentDirEnv:
    def __init__(self, path) -> None:
        parent = Path(path).absolute()

        name = datetime.now().strftime("%Y%m%d_%H%M%S")
        experiment_path = parent / name

        experiment_path.mkdir(parents=True)
        logging.info(f"Store experiment output in folder {experiment_path}")

        self.path = experiment_path

    def __enter__(self):
        self.old_dir = Path(os.getcwd()).absolute()
        os.chdir(self.path)
        return self.path

    def __exit__(self, t, v, tb):
        os.chdir(self.old_dir)


class NestedNamespace(SimpleNamespace):
    def __init__(self, dictionary, **kwargs):
        super().__init__(**kwargs)
        for key, value in dictionary.items():
            if isinstance(value, dict):
                self.__setattr__(key, NestedNamespace(value))
            else:
                self.__setattr__(key, value)


def get_binary_size(program: SourceProgram, setting: CompilationSetting):
    return setting.compile_program(
        program, ObjectCompilationOutput(None)
    ).output.text_size()


def get_ratio(program: SourceProgram, setting: CompilationSetting):
    source_size = len(program.code)

    binary_size = get_binary_size(program, setting)
    return binary_size / source_size


def get_config_and_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, help="Path to config file")

    args = parser.parse_args()
    config = import_config(args.config)
    return args, config


def import_config(config_path):
    if config_path is None:
        p = Path("config/default.json")
        p = p.absolute()
        if p.exists():
            config_path = p
        else:
            raise Exception(f"Found no config.json file at {p}!")
    else:
        if not Path(config_path).is_file():
            raise Exception(f"Found no config.json file at {config_path}!")

    with open(config_path, "r") as f:
        config_dict = json.load(f)

    config = NestedNamespace(config_dict)

    return config
