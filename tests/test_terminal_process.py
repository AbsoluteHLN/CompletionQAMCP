"""Synthetic operator input over real PTY; not real user authorization evidence."""
import os, select, subprocess, sys, tempfile, time, unittest
if os.name == "posix": import pty
from pathlib import Path
@unittest.skipUnless(os.name == "posix", "PTY fixtures require POSIX; Windows console must be tested natively")
class TerminalTests(unittest.TestCase):
 def exercise(self, approval):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'a.py').write_text('x=1');master,slave=pty.openpty()
   process=subprocess.Popen([sys.executable,'-m','completion_plugin.cli','wizard','--root',d,'--state',str(root/'state'),'--artifact','a.py'],stdin=slave,stdout=slave,stderr=slave)
   os.close(slave);data=b''
   try:
    os.write(master,('Check syntax\nyes\nhttps://docs.python.org\nacknowledge\nlocal\n'+approval+'\n').encode())
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
     ready,_,_=select.select([master],[],[],.1)
     if ready:
      try: chunk=os.read(master,65536)
      except OSError:break
      data+=chunk
     if process.poll() is not None and not ready:break
    process.wait(timeout=2)
    self.assertEqual(process.returncode,0,data.decode())
   finally:
    if process.poll() is None:process.kill();process.wait()
    os.close(master)
   return data.decode()
 def test_real_terminal_success_fixture(self):self.assertIn('"status": "pass"',self.exercise('APPROVE 2'))
 def test_real_terminal_denial_fixture(self):self.assertIn('"status": "cancelled"',self.exercise('NO'))
