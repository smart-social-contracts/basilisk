from basilisk import __version__
from pathlib import Path
from setuptools import setup  # type: ignore

setup(
    name="ic-basilisk",
    version=__version__,
    package_data={"basilisk": [
        "compiler/**/*.py",
        "compiler/**/*.rs",
        "compiler/**/*.toml",
        "compiler/**/*.c",
        "compiler/**/*.h",
        "compiler/**/*.sh",
        "compiler/**/*.json",
        "compiler/**/*.wasm",
        "compiler/**/*.a",
        "compiler/**/*.pdf",
        "compiler/**/LICENSE*",
        "canisters/**",
        "py.typed",
    ]},
    include_package_data=True,
    packages=["basilisk", "basilisk.os"],
    install_requires=["modulegraph==0.19.3"],
    extras_require={
        "shell": ["asyncssh"],
        "test": ["pytest"],
    },
    entry_points={
        "console_scripts": [
            "basilisk=basilisk.cli:main",
        ],
    },
    long_description=Path("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
)
