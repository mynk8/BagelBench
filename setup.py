# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pathlib import Path
import os

from setuptools import Extension, find_namespace_packages, setup

USE_CYTHON = os.environ.get("USE_CYTHON", "0") == "1"

ext_modules = []

if USE_CYTHON:
    from Cython.Build import cythonize

    print(f"USE_CYTHON: {USE_CYTHON}")

    extensions = []
    src_dir = Path("artemis")

    # Recursively find all .py files inside the artemis/ directory for optional acceleration
    for py_file in src_dir.rglob("*.py"):
        rel_path = py_file.relative_to(src_dir)
        mod_parts = ("artemis",) + rel_path.with_suffix("").parts
        module_name = ".".join(mod_parts)

        if module_name in (
            "artemis.__init__",
            "artemis._legacy_imports",
            "artemis.main",
            "artemis.mcp.adb_server",
            "artemis.mcp.xml_search_server",
        ):
            continue

        extensions.append(Extension(module_name, [str(py_file)]))

    ext_modules = cythonize(
        extensions,
        compiler_directives={"language_level": "3"},
        build_dir="build/cythonized",
    )

setup(
    # Name and version come from pyproject.toml.
    packages=find_namespace_packages(
        include=[
            "artemis",
            "artemis.*",
            "apps",
            "apps.harness_server",
            "apps.harness_server.*",
            "third_party.*",
        ],
    ),
    package_data={
        "artemis": ["**/*.json", "**/*.md"],
        "artemis.resources": ["config/*.jsonc"],
        # third_party has no __init__.py (namespace package), so it does not clash
        # with other distributions that also ship a third_party directory.
        "third_party.mobile_use": ["LICENSE", "NOTICE", "METADATA", "**/*.md"],
    },
    include_package_data=False,
    ext_modules=ext_modules,
    exclude_package_data={"": ["*.c", "*.pyx", "*.pxd", "*.cpp"]},
)
