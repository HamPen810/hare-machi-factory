"""Exact integer storage in SQLite, including values beyond signed 64 bits."""
import sqlite3
import sys
# Extremely large exact integer counters must remain JSON-serializable.
if hasattr(sys, "set_int_max_str_digits"):
 sys.set_int_max_str_digits(0)

def pack(n):
 n=int(n)
 return n if -(1<<63)<=n<(1<<63) else b'big:'+str(n).encode()
def unpack(v):return int(v[4:]) if isinstance(v,bytes) and v.startswith(b'big:') else v
class ExactRow:
 def __init__(self,cursor,row):self.names=[c[0] for c in cursor.description];self.values=[unpack(v) for v in row]
 def keys(self):return self.names
 def __getitem__(self,k):return self.values[self.names.index(k)] if isinstance(k,str) else self.values[k]
 def __iter__(self):return iter(self.values)
def setup(db):
 sqlite3.register_adapter(int,pack)
 db.row_factory=ExactRow
 db.create_function('badd',2,lambda a,b:pack(int(unpack(a))+int(unpack(b))))
 db.create_function('bsub',2,lambda a,b:pack(int(unpack(a))-int(unpack(b))))
 db.create_function('bge',2,lambda a,b:int(int(unpack(a))>=int(unpack(b))))
 class Sum:
  def __init__(self):self.n=0
  def step(self,n):self.n+=int(unpack(n) or 0)
  def finalize(self):return pack(self.n)
 db.create_aggregate('bsum',1,Sum)
def wire(v):
 if type(v) is int and abs(v)>9007199254740991:return str(v)
 if isinstance(v,dict):return {k:wire(n) for k,n in v.items()}
 if isinstance(v,(list,tuple)):return [wire(n) for n in v]
 return v
