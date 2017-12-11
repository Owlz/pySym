import z3
import logging
from .. import pyState
from . import decorators

logger = logging.getLogger("ObjectManager:Int")

import os


class Int:
    """
    Define an Int
    """
    
    def __init__(self,varName,ctx,count=None,value=None,state=None,increment=False,uuid=None,clone=None):
        """
        Args:
            varName (str): Name for this variable.
            ctx (int): What context is this variable in?
            count (int, optional): How many of this variable iterations have we seen? Defaults to 0.
            value (int, optional): Staic value for this Int.
            state (pySym.pyState.State, optional): State object for this Int to reside in.
            increment (bool, optional): Should we increment this value right away. Defaults to False.
            uuid (int, optional): UUID for this object generated at creation time.
            clone (pySym.pyObjectManager, optional): Object that this object is cloning. Do not set manually.
        """

        assert type(varName) is str, "Unexpected varName type of {}".format(type(varName))
        assert type(ctx) is int, "Unexpected ctx type of {}".format(type(ctx))
        assert type(value) in [type(None),int], "Unexpected value type of {}".format(type(value))
        assert type(uuid) in [bytes, type(None)], "Unexpected uuid type of {}".format(type(uuid))

        self.count = 0 if count is None else count
        self.varName = varName
        self.ctx = ctx
        self.value = value
        self.uuid = os.urandom(32) if uuid is None else uuid
        self._clone = clone
        
        if state is not None:
            self.setState(state)

        if increment:
            self.increment()


    def __deepcopy__(self,_):
        return self.copy()

    def __copy__(self):
        return self.copy()

    def copy(self):
        return Int(
            varName = self.varName,
            ctx = self.ctx,
            count = self.count,
            value = self.value,
            state = self.state if hasattr(self,"state") else None,
            uuid = self.uuid,
            clone = self._clone.copy() if self._clone is not None else None
        )

    def setState(self,state):
        """
        This is a bit strange, but State won't copy correctly due to Z3, so I need to bypass this a bit by setting State each time I copy
        """
        assert type(state) == pyState.State

        self.state = state
        if self._clone is not None:
            self._clone.setState(state)


    def increment(self):
        # If we're incrementing, remove our clone
        self._clone = None
        self.value = None
        self.count += 1
        
    @decorators.as_clone
    def getZ3Object(self):
        """
        Returns the z3 object for this variable
        """
        if self.value is None:
            return z3.Int("{0}{1}@{2}".format(self.count,self.varName,self.ctx),ctx=self.state.solver.ctx)
        
        return z3.IntVal(self.value)

    
    def _isSame(self,value=None,*args,**kwargs):
        """
        Checks if variables for this object are the same as those entered.
        Assumes checks of type will be done prior to calling.
        """
        if value == self.value:
            return True
        return False


    @decorators.as_clone
    def isStatic(self):
        """
        Returns True if this object is a static variety (i.e.: IntVal(12)).
        Also returns True if object has only one possibility
        """
        # If this is a static int
        if self.value is not None:
            return True
        
        # If this is an integer with only one possibility
        if len(self.state.any_n_int(self,2)) == 1:
            return True

        return False

    @decorators.as_clone
    def getValue(self):
        """
        Resolves the value of this integer. Assumes that isStatic method is called
        before this is called to ensure the value is not symbolic
        """
        if self.value is not None:
            return self.value
        
        return self.state.any_int(self)

    def setTo(self,var):
        """
        Sets this Int object to be equal/copy of another. Type can be int or Int
        """
        # Floats are OK so long as they are equal to an int
        if type(var) is float:
            if int(var) == var:
                var = int(var)
            else:
                err = "Attempting to set float {0} to int {1}!".format(var,int(var))
                logger.error(err)
                raise Exception(err)

        assert type(var) in [Int, int, z3.z3.ArithRef, Char], "Unexpected type for var of {0}".format(type(var))

        # Add the constraints

        # If we're not in the solver, we can play some tricks to make things faster
        if not z3Helpers.varIsUsedInSolver(self.getZ3Object(),self.state.solver):

            # If we're adding a static variety, don't clutter up the solver
            if type(var) is int:
                self._clone = None # We're static, no more clone
                self.value = var            
                return

            # If var is static and not being used in any expressions
            elif type(var) in [Int, Char]:
                
                # If the var is static, then we can be static too. #win
                if var.isStatic():
                    if type(var) is Int:
                        self.value = var.getValue()
                    else:
                        self.value = ord(var.getValue())
                    self._clone = None # We're static, no more clone
                    return

                # Clone the object.
                else:

                    logger.debug("Int {}: Setting clone to {}".format(self.varName, var.varName))
                    self._clone = var
                    return

        ## At this point, we know that our own variable is in the solver already, need to add this to the solver        

        if type(var) in [int, z3.z3.ArithRef]:
            obj = var
        elif var.isStatic():
            obj = var.getValue()
            # If it was a Char, just turn it into an int
            if type(obj) == str:
                obj = ord(obj)
        else:
            obj = var.getZ3Object()

        # If we're setting this to a variable, make sure we're not set as static
        self.value = None
        self.state.addConstraint(self.getZ3Object() == obj)

    @decorators.as_clone
    def __str__(self):
        """
        str will change this object into a possible representation by calling state.any_int
        """
        return str(int(self))

    @decorators.as_clone
    def __int__(self):
        """int: Possible integer value of this object."""
        return self.state.any_int(self)

    @decorators.as_clone
    def mustBe(self,var):
        """
        Test if this Int must be equal to another variable
        Returns True or False
        """
        if not self.canBe(var):
            return False

        # Can we be something else?
        if len(self.state.any_n_int(self,2)) == 2:
            return False

        # Can the other var be something else?
        if len(self.state.any_n_int(var,2)) == 2:
            return False
        
        #return False
        return True

    @decorators.as_clone
    def canBe(self,var):
        """
        Test if this Int can be equal to the given variable
        Returns True or False
        """
        
        if type(var) not in [Int, BitVec, Char, int]:
            return False
        
        # Ask the solver
        s = self.state.copy()

        if type(var) in [Int, BitVec, Char]:
            s.addConstraint(self.getZ3Object() == var.getZ3Object())
        else:
            s.addConstraint(self.getZ3Object() == var)
        
        if s.isSat():
            return True
        
        return False

    @property
    @decorators.as_clone_property
    def is_unconstrained(self):
        """bool: Returns True if this Int has no external constraints applied to it. False otherwise."""
        return not z3Helpers.varIsUsedInSolver(var=self.getZ3Object(),solver=self.state.solver)

    @property
    @decorators.as_clone_property
    def is_constrained(self):
        """bool: Opposite of is_unconstrained."""
        return not self.is_unconstrained

from .BitVec import BitVec
from .Char import Char
from .Ctx import Ctx
from ..pyState import z3Helpers
