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

test1 = """
def test2():
    return 5

def test():
    return test2() + test2()

x = test()
z = 1
"""

def test_pyPath_stepThroughProgram():
    b = ast.parse(test1).body
    p = Path(b,source=test1)
    pg = PathGroup(p)
    pg.step()
    pg.step()
    pg.step()
    pg.step()
    pg.step()
    pg.step()
    pg.step()
    pg.step()
    pg.step()
    pg.step()
    pg.step()

    assert len(pg.active) == 0
    assert len(pg.completed) == 1
    assert len(pg.errored) == 0
    assert len(pg.deadended) == 0
    
    assert pg.completed[0].state.any_int('x') == 10
    assert pg.completed[0].state.any_int('z') == 1

