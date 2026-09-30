import unittest,tempfile,pathlib,json
from demo import recommend,execute,run
class BehaviorTests(unittest.TestCase):
 def test_missing_is_not_zero(self):
  self.assertEqual(recommend(None,False,'2026-09','2026-09')['action'],'hold')
  self.assertEqual(recommend(0,True,'2026-09','2026-09')['action'],'revise')
 def test_period_and_threshold(self):
  self.assertEqual(recommend(120,True,'2026-08','2026-09')['action'],'hold')
  self.assertEqual(recommend(120,True,'2026-09','2026-09')['action'],'maintain')
 def test_invalid_data_rejected(self):
  for value in [-1,True,'0']:
   with self.assertRaises(ValueError):recommend(value,True,'2026-09','2026-09')
 def test_recovery_and_approval(self):
  with tempfile.TemporaryDirectory() as f:
   p=pathlib.Path(f)/'state.json'
   with self.assertRaises(RuntimeError):execute(p,'job',20,10,'prepare')
   self.assertEqual(json.loads(p.read_text())['job']['completed'],['check'])
   self.assertEqual(execute(p,'job',20,11),'done')
   snapshot=p.read_bytes()
   self.assertEqual(execute(p,'job',20,12),'skipped')
   self.assertEqual(p.read_bytes(),snapshot)
   with self.assertRaises(PermissionError):execute(p,'another',12,12)
   self.assertEqual(p.read_bytes(),snapshot)
 def test_csv_outputs_separate(self):
  self.assertEqual(run()['csv'][0],{'id':'synthetic-example','management_balance':180000,'deposit_difference':20000})
if __name__=='__main__':unittest.main()
