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

"""Recognize Cython function types when validating device models."""


class _CyFunctionDetectorMeta(type):
    """Metaclass for detecting cython compiled functions."""

    def __instancecheck__(cls, instance):
        name = type(instance).__name__
        return (
            name
            in (
                "cyfunction",
                "cython_function_or_method",
                "builtin_function_or_method",
            )
            or "cyfunction" in name.lower()
        )


# pylint: disable=too-few-public-methods
class CyFunctionDetector(metaclass=_CyFunctionDetectorMeta):
    """Detector for cython compiled functions."""
