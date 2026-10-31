#!/usr/bin/env python3
"""Frozen AndroidWorld-derived QA pilot. Generation needs AndroidWorld; replay does not."""
import argparse
from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

VERSION = 'artemis-qa-pilot/v1'
REVISION = '55ddaf5edc6f6c25673aed343907d5b9dca66f84'
PROFILES = {
 'SimpleCalendarAddOneEvent': {'family':'calendar.record_integrity','app':'Simple Calendar Pro','fields':['title','start_ts','end_ts','description'],'mutations':[('delete_target',None),('change_value','title'),('shift_date','start_ts'),('truncate_text','description'),('change_value','title')]},
 'ExpenseAddSingle': {'family':'expense.record_integrity','app':'Pro Expense','fields':['name','amount','category','note'],'mutations':[('delete_target',None),('change_value','name'),('change_value','amount'),('truncate_text','note'),('change_value','amount')]},
 'RecipeAddSingleRecipe': {'family':'recipe.record_integrity','app':'Broccoli','fields':['title','description','servings','preparationTime','ingredients','directions'],'mutations':[('delete_target',None),('change_value','title'),('truncate_text','directions'),('change_value','servings'),('change_value','title')]},
}


def canonical(value):
 return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))


def sha(value):
 return hashlib.sha256(canonical(value).encode()).hexdigest()


def strict_oracle(before, after, reference, fields):
 """Exact listed fields, one distinct match per target, and unchanged prior records."""
 remaining = list(after)
 for row in before:
  try: remaining.remove(row)
  except ValueError: return False
 if len(remaining) != len(reference): return False
 for expected in reference:
  matches = [i for i,row in enumerate(remaining) if all(field in row and field in expected and row[field]==expected[field] for field in fields)]
  if len(matches)!=1: return False
  remaining.pop(matches[0])
 return not remaining


def prompt(task_name, row):
 profile = PROFILES[task_name]
 criteria = {field:row[field] for field in profile['fields']}
 hints={}
 for field in ('start_ts','end_ts'):
  if field in row: hints[field]=datetime.fromtimestamp(row[field],timezone.utc).isoformat()
 if task_name=='ExpenseAddSingle':
  hints['amount']=f"${row['amount']/100:.2f}"
  hints['category']={1:'Others',2:'Income',3:'Food',4:'Housing',5:'Social',6:'Entertainment',7:'Transportation',8:'Clothes',9:'Health Care',10:'Education',11:'Donation'}.get(row['category'],'Unknown')
 return (f"Inspect the existing record in {profile['app']}. Verify that exactly one target record has every expected field below. "
         "Navigate and search as needed. Do not add, edit, or delete records. "
         "Return PASS only when every listed field matches; FAIL when a mismatch or missing record is established; "
         "INCONCLUSIVE when the available evidence cannot establish either. "
         "Timestamp values are Unix time in UTC: calendar timestamps are seconds. Expense amount is in cents and category is the app's category ID.\n"
         +json.dumps({'expected_fields':criteria,'display_hints':hints},ensure_ascii=False,sort_keys=True))


def generate(seed=42, cases_per_app=10, edition='pilot'):
 if type(cases_per_app) is not int or not 1 <= cases_per_app <= 1000:
  raise ValueError('cases_per_app must be an integer in [1, 1000]')
 from androidworld_suite import get_task_types, normalize, androidworld_revision
 import numpy as np
 if androidworld_revision()!=REVISION: raise ValueError('Unexpected AndroidWorld revision')
 registry = get_task_types()
 instances=[];trials=[]
 for task_name,profile in PROFILES.items():
  for index in range(cases_per_app):
   case_seed=seed+index
   random.seed(case_seed);np.random.seed(case_seed%(2**32))
   params=registry[task_name].generate_random_params();params['seed']=case_seed
   params=normalize(params)
   if len(params['row_objects'])!=1: raise ValueError('Pilot requires one target record')
   operation,field=profile['mutations'][index%5]
   if operation=='truncate_text' and (not isinstance(params['row_objects'][0].get(field),str) or len(params['row_objects'][0][field])<2):
    raise ValueError(f'Inapplicable mutation for {task_name}, seed {case_seed}')
   instance={'task_name':task_name,'family':profile['family'],'seed':case_seed,'params':params,'oracle_fields':profile['fields'],'operation':operation,'field':field,'test_prompt':prompt(task_name,params['row_objects'][0]),'dataset_revision':REVISION,'source_state_origin':'pinned_androidworld_task_parameter_generator','fault_path_origin':'deterministic_single_fault_mutation_of_generated_target','oracle_contract':'exact-fields-preserve-before/v1'}
   instance['pair_id']='pair-'+sha(instance)[:20]
   instances.append(instance)
   for variant in ('control','fault'):
    trials.append({'trial_id':instance['pair_id']+'-'+variant,'pair_id':instance['pair_id'],'family':profile['family'],'variant':variant})
 random.Random(seed).shuffle(trials)
 manifest={'schema_version':VERSION,'edition':edition,'root_seed':seed,'cases_per_app':cases_per_app,'dataset_revision':REVISION,'oracle_version':'exact-fields-preserve-before/v1','instances':instances,'trials':trials,'admission':'setup_confirmed AND visibility_confirmed AND criterion_matched AND no protected state change AND valid pre/post truth','counts':{'families':len({item['family'] for item in instances}),'instances':len(instances),'trials_per_condition_repeat':len(trials)}}
 manifest['suite_id']='suite-'+sha(manifest)[:20]
 return manifest


def load_manifest(path):
 manifest=json.loads(Path(path).read_text())
 identity=dict(manifest);suite_id=identity.pop('suite_id')
 if suite_id!='suite-'+sha(identity)[:20]: raise ValueError('Pilot manifest checksum mismatch')
 if manifest['schema_version']!=VERSION: raise ValueError('Unsupported pilot version')
 return manifest


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--seed',type=int,default=42);parser.add_argument('--cases-per-app',type=int,default=10);parser.add_argument('--edition',default='pilot');parser.add_argument('--out',type=Path,required=True)
 args=parser.parse_args();manifest=generate(args.seed,args.cases_per_app,args.edition)
 args.out.parent.mkdir(parents=True,exist_ok=True)
 args.out.write_text(json.dumps(manifest,sort_keys=True,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'suite_id':manifest['suite_id'],**manifest['counts']}))
