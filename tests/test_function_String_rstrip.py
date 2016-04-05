import sys, os
myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, myPath + '/../')

import logging
import Colorer
logging.basicConfig(level=logging.DEBUG,format='%(name)s - %(levelname)s - %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')

import ast
import z3
from pyPath import Path
from pyPathGroup import PathGroup
import pytest
from pyObjectManager.Int import Int
from pyObjectManager.Real import Real
from pyObjectManager.BitVec import BitVec
from pyObjectManager.List import List

test1 = """
x = "test ".rstrip()
y = "test".rstrip()
z = "test".rstrip("t")
d = "test".rstrip("st")
"""

test2 = """
s = pyState.String(8)
x = "test1".rstrip(str(s.index('a')))
"""

test3 = """
s = pyState.String(2)
x = "testt"
x = x.rstrip(s)
"""

test4 = """
s = pyState.String(8)
x = s.rstrip("x")
"""

test5 = """
s = "mee"
s2 = pyState.String(1)
x = ''.join([x for x in s.rstrip(s2)])
"""

def test_function_String_rstrip_Char():
    b = ast.parse(test5).body
    p = Path(b,source=test5)
    pg = PathGroup(p)

    pg.explore()
    assert len(pg.completed) == 2
    assert set([p.state.any_str('x') for p in pg.completed]) == {"m","mee"}


def test_function_String_rstrip_symbolicStrip():
    b = ast.parse(test3).body
    p = Path(b,source=test3)
    pg = PathGroup(p)

    pg.explore()
    assert len(pg.completed) == 3
    o = [p.state.any_str('x') for p in pg.completed]
    o.sort()
    # 3 cases. 1) both chars miss, 2) one char hit's "t" and the other misses. 3) one hits
    # "t" and the other hits "s"
    assert o == ['te', 'tes', 'testt']

    b = ast.parse(test4).body
    p = Path(b,source=test4)
    pg = PathGroup(p)

    pg.explore()
    assert len(pg.completed) == 9

    # TODO: This is a brittle match..
    o = [p.state.any_str('s') for p in pg.completed]
    o.sort()
    assert not o[0].endswith("x")
    for x in range(1,8):
        assert o[x].endswith("x"*x)
    #['\x00\x00\x00\x00\x00\x00\x00\x00', '\x00\x00\x00\x00\x00\x00\x00x', '\x00\x00\x00\x00\x00\x00xx', '\x00\x00\x00\x00\x00xxx', '\x00\x00\x00\x00xxxx', '\x00\x00\x00xxxxx', '\x00\x00xxxxxx', '\x00xxxxxxx', 'xxxxxxxx']



def test_function_String_rstrip_statesplit():
    b = ast.parse(test2).body
    p = Path(b,source=test2)
    pg = PathGroup(p)

    pg.explore()
    assert len(pg.completed) == 8
    o = [p.state.any_str('x') for p in pg.completed]
    o.sort()
    assert o == ['test', 'test1', 'test1', 'test1', 'test1', 'test1', 'test1', 'test1']


def test_function_String_rstrip():
    b = ast.parse(test1).body
    p = Path(b,source=test1)
    pg = PathGroup(p)

    pg.explore()
    assert len(pg.completed) == 1
    
    assert pg.completed[0].state.any_str('x') == "test ".rstrip()
    assert pg.completed[0].state.any_str('y') == "test".rstrip()
    assert pg.completed[0].state.any_str('z') == "test".rstrip("t")
    assert pg.completed[0].state.any_str('d') == "test".rstrip("st")

