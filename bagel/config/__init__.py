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

"""Device and host configuration."""

from bagel.config.paths import (
    ROOT_DIR,
    WORKSPACE_ROOT,
    CONFIG_DIR,
    GLOBAL_APP_DIR,
    TRACES_PATH,
    DB_PATH,
    get_app_dir,
    get_traces_dir,
    get_default_traces_path,
    get_env_file,
    get_temp_dir,
    get_data_engine_db_path,
    is_source_checkout,
    is_frozen_bundle,
)
from bagel.config.settings import Settings, settings
