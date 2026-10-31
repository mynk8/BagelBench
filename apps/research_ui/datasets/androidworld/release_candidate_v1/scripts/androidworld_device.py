#!/usr/bin/env python3
"""Isolated AndroidWorld device bridge. Run with an AndroidWorld Python environment."""
import dataclasses
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sqlite3
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qa_pilot import PROFILES, strict_oracle, prompt

TASKS = {
    'SimpleCalendarAddOneEvent': ('title', 'description', 'start_ts'),
    'ExpenseAddSingle': ('name', 'amount', 'note'),
    'RecipeAddSingleRecipe': ('title', 'directions', 'servings'),
}


def encode(value):
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    raise TypeError(type(value).__name__)


def digest(rows):
    canonical = sorted(json.dumps(row, default=encode, sort_keys=True) for row in rows)
    return hashlib.sha256(json.dumps(canonical, separators=(',', ':')).encode()).hexdigest()


#: Bumped whenever a fault operation writes different values; recorded with every seed.
MUTATION_VERSION = 'near-miss/v2'


def near_miss_text(old):
    """A plausible typo of ``old``: swap two adjacent letters in its longest word.

    Deterministic, so a frozen instance always seeds the same fault. Unlike a sentinel
    string, the result does not announce that the record was mutated, yet any exact
    field comparison still detects it.
    """
    words = old.split(' ')
    index = max(range(len(words)), key=lambda i: (len(words[i]), -i))
    word = words[index]
    for i in range(len(word) // 2, len(word) - 1):
        if word[i] != word[i + 1] and word[i].isalpha() and word[i + 1].isalpha():
            words[index] = word[:i] + word[i + 1] + word[i] + word[i + 2:]
            return ' '.join(words)
    return old[:-1] if len(old) > 1 else old + 's'


def mutate_database(task, env, target, operation, field):
    """Apply one parameterized update to the actual emulator database."""
    from android_world.env import adb_utils
    from android_world.utils import file_utils
    adb_utils.close_app(task.app_name_with_db, env.controller)
    key = task.db_key
    for identifier in (task.table_name, key, field or key):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', identifier):
            raise ValueError('Invalid database identifier')
    with env.controller.pull_file(task.db_path) as directory:
        local = file_utils.convert_to_posix_path(directory, os.path.basename(task.db_path))
        with closing(sqlite3.connect(local)) as conn, conn:
            if operation == 'delete_target':
                cursor = conn.execute(f'DELETE FROM "{task.table_name}" WHERE "{key}"=?', (getattr(target, key),))
            else:
                old = getattr(target, field)
                if operation == 'truncate_text':
                    if not isinstance(old, str) or len(old) < 2:
                        raise ValueError('Field has no truncatable text')
                    new = old[:max(1, len(old)//2)]
                elif operation == 'change_value':
                    new = old + 100 if isinstance(old, (int, float)) else near_miss_text(old)
                elif operation == 'shift_date':
                    if field != 'start_ts':
                        raise ValueError('Date mutation supports calendar start_ts only')
                    new = old + 86400
                else:
                    raise ValueError('Unsupported mutation')
                if operation == 'shift_date':
                    cursor = conn.execute(f'UPDATE "{task.table_name}" SET start_ts=?, end_ts=? WHERE "{key}"=?', (new,getattr(target,'end_ts')+86400,getattr(target,key)))
                else:
                    cursor = conn.execute(f'UPDATE "{task.table_name}" SET "{field}"=? WHERE "{key}"=?', (new, getattr(target, key)))
            if cursor.rowcount != 1:
                raise ValueError('Mutation must affect exactly one target row')
        env.controller.push_file(local, task.db_path)
    adb_utils.close_app(task.app_name_with_db, env.controller)


def run(request):
    # AndroidEnv logs inherited environment variables at INFO.
    from absl import logging
    logging.set_verbosity(logging.WARNING)
    # Avoid repeated unbounded downloads by using the locally cached upstream APK.
    from android_env.wrappers import a11y_grpc_wrapper
    forwarder = Path('/tmp/android_world/app_data/accessibility_forwarder.apk')
    if forwarder.is_file():
        a11y_grpc_wrapper._get_accessibility_forwarder_apk = forwarder.read_bytes
    from android_world import registry
    from android_world.env import env_launcher, adb_utils
    name = request['task_name']
    if name not in TASKS:
        raise ValueError('Task is not in the supported SQLite pilot')
    serial = request['device_serial']
    if not re.fullmatch(r'emulator-\d+', serial):
        raise ValueError('Use a dedicated AndroidWorld emulator')
    task_registry = registry.TaskRegistry()
    cls = task_registry.get_registry(task_registry.ANDROID_WORLD_FAMILY)[name]
    revision = subprocess.run(['git', '-C', str(Path(__import__('android_world').__file__).resolve().parent.parent), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    if revision != request['dataset_revision']:
        raise ValueError('AndroidWorld source revision changed')
    if request['mode'] not in ('prepare', 'check'):
        raise ValueError('Unsupported fixture mode')
    from androidworld_grpc import configure_token_auth
    configure_token_auth(int(serial.split('-')[1]), request.get('grpc_port', 8554))
    env = env_launcher.load_and_setup_env(console_port=int(serial.split('-')[1]), adb_path=request['adb_path'], grpc_port=request.get('grpc_port',8554), emulator_setup=False, freeze_datetime=request['mode'] == 'prepare')
    try:
        if request['mode'] == 'prepare':
            random.seed(request['seed'])
            import numpy as np
            np.random.seed(request['seed'] % (2**32))
            params = request.get('frozen_instance', {}).get('params')
            if params is not None:
                for key in ('row_objects','noise_row_objects'):
                    if key in params:
                        params[key] = [cls.row_type(**row) for row in params[key]]
            else:
                params = cls.generate_random_params()
            params['seed'] = request['seed']
            task = cls(params)
            task.initialize_task(env)
            task.add_rows(params['row_objects'], env)
            fields = PROFILES[name]['fields']
            def exact():
                return strict_oracle([encode(r) for r in task.before], [encode(r) for r in task.list_rows(env)], [encode(r) for r in params['row_objects']], fields)
            if task.is_successful(env) != 1.0 or not exact():
                raise ValueError('Correct-state oracle failed; refusing to create a pair')
            baseline = task.list_rows(env)
            reference = params['row_objects'][0]
            title_field = TASKS[name][0]
            candidates = [r for r in baseline if getattr(r,title_field)==getattr(reference,title_field)]
            if len(candidates) != 1:
                raise ValueError('Target record is not unique')
            if request['fault_seed']:
                field = request.get('field') or title_field
                if field not in TASKS[name]:
                    raise ValueError('Field is not in the supported mutation fields')
                mutate_database(task, env, candidates[0], request['operation'], field)
            rows = task.list_rows(env)
            upstream_satisfied = task.is_successful(env) == 1.0
            target_satisfied = exact()
            if target_satisfied == request['fault_seed']:
                raise ValueError('Mutation did not produce the expected oracle outcome')
            adb_utils.launch_app(task.app_name_with_db, env.controller)
            snapshot = json.loads(json.dumps({'params':params,'before':task.before, 'dataset_revision':revision, 'oracle_fields':fields},default=encode))
            goal = str(task.goal)
            return {'snapshot':snapshot,'baseline_rows':json.loads(json.dumps(baseline,default=encode)), 'observed_rows':json.loads(json.dumps(rows,default=encode)), 'state_sha256':digest(rows), 'target_satisfied':target_satisfied,'baseline_oracle_confirmed':True,'fault_confirmed':not target_satisfied,'dataset_revision':revision,'original_action_goal':goal,'upstream_oracle_satisfied':upstream_satisfied, 'oracle_version':'exact-fields-preserve-before/v1', 'mutation_version':MUTATION_VERSION, 'test_prompt':request.get('frozen_instance',{}).get('test_prompt') or prompt(name,encode(reference))}
        snapshot = request['snapshot']
        if snapshot.get('dataset_revision') != revision:
            raise ValueError('Fixture was prepared with a different AndroidWorld revision')
        params = snapshot['params']
        for key in ('row_objects','noise_row_objects'):
            if key in params:
                params[key] = [cls.row_type(**row) for row in params[key]]
        task = cls(params)
        task.before = [cls.row_type(**row) for row in snapshot['before']]
        task.initialized = True
        rows = task.list_rows(env)
        fields = snapshot.get('oracle_fields', PROFILES[name]['fields'])
        if fields != PROFILES[name]['fields']:
            raise ValueError('Oracle field specification changed')
        correct = strict_oracle(snapshot['before'], [encode(r) for r in rows], [encode(r) for r in params['row_objects']], fields)
        return {'target_satisfied':correct,'upstream_oracle_satisfied':task.is_successful(env)==1.0,'observed_rows':json.loads(json.dumps(rows,default=encode)),'state_sha256':digest(rows)}
    finally:
        env.close()


if __name__ == '__main__':
    request = json.loads(Path(sys.argv[1]).read_text())
    try:
        result = run(request)
    except Exception as error:
        result = {'error':f'{type(error).__name__}: {error}'}
    Path(sys.argv[2]).write_text(json.dumps(result,sort_keys=True))
